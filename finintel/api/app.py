"""The HTTP API: uploads, reports, commentary, pages, review and the human-decision endpoints.

Local only, no authentication (ADR-004). The API never computes a number: it stores a person's
decision, lets the pipeline's own stages re-run, and serves what the database holds. Errors are
`{"detail": {"code", "message"}}` with the status the spec names (413, 415, 422).
"""

from __future__ import annotations

import json
import math
import tempfile
import threading
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import psycopg
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from finintel.api import dashboard as dash
from finintel.api import models as m
from finintel.api.extraction_view import extraction_view
from finintel.cache import StageCache
from finintel.commentary.reported import find_reported_metrics
from finintel.contracts import validate_pack
from finintel.contracts.commentary import Commentary
from finintel.db import jobs, persist
from finintel.ingest import MAX_UPLOAD_BYTES, IngestError, IngestErrorCode
from finintel.parse.cached import cached_text_layer
from finintel.ratios import compute_ratios, pack_sha256, ratio_pack_json
from finintel.review import (
    OverrideError,
    ValueOverride,
    anchored_on_page,
    apply_document_type,
    apply_value_override,
)
from finintel.review.overrides import check_value
from finintel.worker.context import RunContext
from finintel.worker.runner import run_until_idle, submit_pdf
from finintel.worker.stages import STAGES

Connect = Callable[[], psycopg.Connection]
AFTER_EXTRACT = tuple(STAGES[STAGES.index("extract") :])
AFTER_TYPE = ("ratios", "commentary")
_INGEST_STATUS = {
    IngestErrorCode.NOT_A_PDF: 415,
    IngestErrorCode.FILE_TOO_LARGE: 413,
    IngestErrorCode.ENCRYPTED_PDF: 422,
    IngestErrorCode.UNREADABLE_PDF: 422,
}


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


_TEXT_LAYERS_KEPT = 4  # reports whose text layer the page endpoint keeps in memory


def _json_safe(value: Any) -> Any:
    """`value` with every non-finite float (NaN, Infinity) replaced by its name as a string."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(v) for v in value]
    return value


def _stored_name(filename: str | None) -> str:
    """The upload's file name as it is stored: its base name, never empty, "." or "..", and short
    enough for any filesystem (255 bytes); a long name keeps its start and its extension."""
    name = Path(filename or "").name
    if name in ("", ".", ".."):
        return "upload.pdf"  # "..", "/" or "a/.." has no base name to store the file under
    if len(name.encode()) <= _MAX_NAME_BYTES:
        return name
    suffix = Path(name).suffix[:16]
    stem = name[: len(name) - len(suffix)].encode()[: _MAX_NAME_BYTES - len(suffix.encode())]
    return stem.decode(errors="ignore") + suffix


_MAX_NAME_BYTES = 200  # under the 255-byte limit, with room for the store's ".tmp<pid>" suffix


def create_app(
    ctx: RunContext | None = None,
    connect: Connect | None = None,
    *,
    run_inline: bool = False,
    start_worker: bool = False,
) -> FastAPI:
    """`run_inline` runs the worker inside the request (tests, `finintel serve --inline`);
    `start_worker` runs it in a background thread. With neither, a separate worker is expected.
    `ctx` and `connect` may be None only to export the OpenAPI document."""
    stop = threading.Event()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Any:
        thread = None
        if start_worker and ctx is not None and connect is not None:
            thread = threading.Thread(target=_worker_loop, args=(ctx, connect, stop), daemon=True)
            thread.start()
        yield
        stop.set()
        if thread is not None:
            thread.join(timeout=5)

    app = FastAPI(
        title="Financial Report Intelligence",
        version="1.0.0",
        description="A research aid: numbers come from the statement pack, never from a model.",
        lifespan=lifespan,
    )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's own 422 echoes each offending input; a NaN or Infinity there cannot be written
        # as JSON and turned the refusal into a 500. The echo is made JSON-safe, the rest is kept.
        return JSONResponse(
            status_code=422, content={"detail": _json_safe(jsonable_encoder(exc.errors()))}
        )

    def conn_dep() -> Iterator[psycopg.Connection]:
        assert connect is not None, "app was created without a database"
        conn = connect()
        try:
            yield conn
        finally:
            conn.close()

    db = Depends(conn_dep)
    upload_file = File(...)

    def settle(conn: psycopg.Connection) -> None:
        if run_inline and ctx is not None:
            run_until_idle(conn, ctx)

    def doc_row(conn: psycopg.Connection, doc_id: int) -> tuple[Any, ...]:
        row = conn.execute(
            "SELECT id, sha256, filename, page_count, document_type, status, storage_key "
            "FROM documents WHERE id = %s",
            (doc_id,),
        ).fetchone()
        if row is None:
            raise _error(404, "report_not_found", f"no report {doc_id}")
        return tuple(row)

    def latest_pack(conn: psycopg.Connection, doc_id: int) -> tuple[int, int, str, dict[str, Any]]:
        row = conn.execute(
            "SELECT id, version, pack_sha, pack FROM statement_packs WHERE document_id = %s "
            "ORDER BY version DESC LIMIT 1",
            (doc_id,),
        ).fetchone()
        if row is None:
            raise _error(409, "no_pack", "this report has no statement pack yet")
        return int(row[0]), int(row[1]), str(row[2]), dict(row[3])

    # ------------------------------------------------------------------ health

    @app.get("/healthz", response_model=m.HealthOut)
    def healthz() -> m.HealthOut:
        return m.HealthOut(status="ok")

    @app.get("/readyz", response_model=m.HealthOut)
    def readyz(response: Response) -> m.HealthOut:
        checks: dict[str, str] = {}
        try:
            assert connect is not None
            with connect() as conn:
                conn.execute("SELECT 1")
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error: {type(exc).__name__}"
        try:
            assert ctx is not None
            ctx.store.root.mkdir(parents=True, exist_ok=True)
            checks["storage"] = "ok"
        except Exception as exc:
            checks["storage"] = f"error: {type(exc).__name__}"
        checks["azure_di"] = (
            "configured" if ctx is not None and ctx.azure is not None else "not configured"
        )
        checks["llm"] = (
            ctx.provider.name if ctx is not None and ctx.provider is not None else "extractive"
        )
        ok = checks["database"] == "ok" and checks["storage"] == "ok"
        if not ok:
            response.status_code = 503
        return m.HealthOut(status="ok" if ok else "unavailable", checks=checks)

    # ------------------------------------------------------------------ uploads and reports

    @app.post("/uploads", response_model=m.UploadOut, status_code=202,
              responses={200: {"model": m.UploadOut}, 413: {}, 415: {}, 422: {}})  # fmt: skip
    def upload(
        response: Response, file: UploadFile = upload_file, conn: psycopg.Connection = db
    ) -> m.UploadOut:
        assert ctx is not None
        limit = MAX_UPLOAD_BYTES
        data = file.file.read(limit + 1)
        if len(data) > limit:
            raise _error(
                413, IngestErrorCode.FILE_TOO_LARGE.value, f"the limit is {limit // 1_048_576} MB"
            )
        name = _stored_name(file.filename)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / name
            path.write_bytes(data)
            try:
                from finintel.ingest import sha256_file

                sha = sha256_file(path)
                existing = conn.execute(
                    "SELECT id FROM documents WHERE sha256 = %s", (sha,)
                ).fetchone()
                doc_id = submit_pdf(conn, ctx, path)
            except IngestError as exc:
                raise _error(_INGEST_STATUS[exc.code], exc.code.value, exc.message) from exc
        settle(conn)
        if existing is not None:
            response.status_code = 200
        row = doc_row(conn, doc_id)
        return m.UploadOut(
            id=doc_id, sha256=str(row[1]), status=str(row[5]), duplicate=existing is not None
        )

    @app.get("/reports", response_model=list[m.ReportSummary])
    def list_reports(conn: psycopg.Connection = db) -> list[m.ReportSummary]:
        """Every report, newest first, with what a list needs to show (name, period, status, what
        is waiting for a person). No figures: those are read from the report itself."""
        rows = conn.execute(
            """
            SELECT d.id, d.filename, d.document_type, d.status, d.page_count, d.created_at,
                   p.pack->>'company_name', p.pack->'periods'->0->>'label', p.pack->>'currency',
                   (p.pack->>'unit_scale')::bigint,
                   (SELECT count(*) FROM review_items r WHERE r.document_id = d.id AND r.status = 'open'),
                   (SELECT c.stale FROM commentaries c WHERE c.document_id = d.id
                    ORDER BY c.id DESC LIMIT 1),
                   d.is_sample, p.pack->>'document_type'
            FROM documents d
            LEFT JOIN LATERAL (
                SELECT pack FROM statement_packs s WHERE s.document_id = d.id
                ORDER BY s.version DESC LIMIT 1
            ) p ON true
            ORDER BY d.created_at DESC, d.id DESC
            """
        ).fetchall()
        return [
            m.ReportSummary(
                id=r[0], filename=r[1], document_type=r[2] if r[2] != "other" or not r[13] else r[13],
                status=r[3], page_count=r[4],
                created_at=r[5].isoformat(), company_name=r[6], period_label=r[7], currency=r[8],
                unit_scale=r[9], open_review_items=int(r[10]), stale=bool(r[11]), is_sample=bool(r[12]),
            )
            for r in rows
        ]  # fmt: skip

    @app.get("/dashboard", response_model=m.DashboardOut)
    def get_dashboard(conn: psycopg.Connection = db) -> m.DashboardOut:
        """Every report with what the pipeline produced for it (counts of figures by how they were
        settled, the headline ratios as the engine stored them, cited commentary) and what it is
        waiting for. Newest first."""
        rows = conn.execute(
            """
            SELECT d.id, d.filename, d.document_type, d.status, d.page_count, d.created_at,
                   d.is_sample, p.pack, rp.pack, c.output, c.stale,
                   (SELECT count(*) FROM review_items r
                    WHERE r.document_id = d.id AND r.status = 'open')
            FROM documents d
            LEFT JOIN LATERAL (
                SELECT id, pack FROM statement_packs s WHERE s.document_id = d.id
                ORDER BY s.version DESC LIMIT 1
            ) p ON true
            LEFT JOIN LATERAL (
                SELECT pack FROM ratio_packs r WHERE r.statement_pack_id = p.id
                ORDER BY r.id DESC LIMIT 1
            ) rp ON true
            LEFT JOIN LATERAL (
                SELECT output, stale FROM commentaries k WHERE k.document_id = d.id
                ORDER BY k.id DESC LIMIT 1
            ) c ON true
            ORDER BY d.created_at DESC, d.id DESC
            """
        ).fetchall()
        jobs_by_doc: dict[int, list[m.JobOut]] = {}
        for doc_id, stage, status, attempts, error in conn.execute(
            "SELECT document_id, stage, status, attempts, error_code FROM jobs "
            "ORDER BY document_id, ordinal"
        ).fetchall():
            jobs_by_doc.setdefault(doc_id, []).append(
                m.JobOut(stage=stage, status=status, attempts=attempts, error_code=error)
            )
        cards = []
        for (doc_id, filename, row_type, status, pages, created, sample, pack, ratios, output,
             stale, review) in rows:  # fmt: skip
            doc_type = dash.document_type_of(str(row_type), pack)
            periods = (pack or {}).get("periods") or []
            figures = dash.figure_counts(pack)
            cards.append(
                m.ReportCard(
                    id=doc_id,
                    title=(pack or {}).get("company_name") or Path(filename).stem,
                    filename=filename,
                    document_type=doc_type,
                    status=status,
                    is_sample=bool(sample),
                    created_at=created.isoformat(),
                    page_count=pages,
                    period_label=periods[0].get("label") if periods else None,
                    prior_label=periods[1].get("label") if len(periods) > 1 else None,
                    currency=(pack or {}).get("currency"),
                    unit_scale=(pack or {}).get("unit_scale"),
                    figures=m.FigureCounts(**figures) if figures else None,
                    ratios=[m.RatioHeadline(**r) for r in dash.ratio_headlines(ratios, doc_type)],
                    commentary=(
                        m.CommentaryHeadline(**h)
                        if (h := dash.commentary_headline(output, bool(stale)))
                        else None
                    ),
                    open_review_items=int(review),
                    waiting_for=dash.waiting_for(status, int(review)),
                    jobs=jobs_by_doc.get(doc_id, []),
                )
            )
        return m.DashboardOut(reports=cards, has_samples=any(c.is_sample for c in cards))

    @app.post("/samples", response_model=m.SamplesOut, status_code=202)
    def post_samples(conn: psycopg.Connection = db) -> m.SamplesOut:
        """Add the sample reports: bundled PDFs through the real pipeline, marked as samples."""
        assert ctx is not None
        from finintel.demo import seed

        result = seed(conn, ctx)
        settle(conn)
        return m.SamplesOut(added=result["added"], skipped=result["skipped"], removed=[])

    @app.delete("/samples", response_model=m.SamplesOut)
    def delete_samples(conn: psycopg.Connection = db) -> m.SamplesOut:
        """Remove every sample report. A person's own uploads are never samples."""
        from finintel.demo import clear

        return m.SamplesOut(added=[], skipped=[], removed=clear(conn))

    @app.get("/reports/{report_id}", response_model=m.ReportOut)
    def get_report(report_id: int, conn: psycopg.Connection = db) -> m.ReportOut:
        doc = doc_row(conn, report_id)
        pack_row = conn.execute(
            "SELECT id, version, pack_sha, pack FROM statement_packs WHERE document_id = %s "
            "ORDER BY version DESC LIMIT 1",
            (report_id,),
        ).fetchone()
        ratios = None
        report: dict[str, Any] = {}
        if pack_row is not None:
            ratio_row = conn.execute(
                "SELECT pack FROM ratio_packs WHERE statement_pack_id = %s ORDER BY id DESC LIMIT 1",
                (pack_row[0],),
            ).fetchone()
            ratios = dict(ratio_row[0]) if ratio_row else None
            rep = conn.execute(
                "SELECT report FROM extraction_reports WHERE document_id = %s ORDER BY pack_id DESC LIMIT 1",
                (report_id,),
            ).fetchone()
            report = dict(rep[0]) if rep else {}
        job_rows = conn.execute(
            "SELECT stage, status, attempts, error_code FROM jobs WHERE document_id = %s ORDER BY ordinal",
            (report_id,),
        ).fetchall()
        stale_row = conn.execute(
            "SELECT stale FROM commentaries WHERE document_id = %s ORDER BY id DESC LIMIT 1",
            (report_id,),
        ).fetchone()
        pack = dict(pack_row[3]) if pack_row else None
        return m.ReportOut(
            id=report_id, sha256=str(doc[1]), filename=str(doc[2]), page_count=int(doc[3]),
            document_type=str(doc[4]), status=str(doc[5]),
            pack_version=int(pack_row[1]) if pack_row else None,
            pack_sha=str(pack_row[2]) if pack_row else None,
            pack=pack, ratios=ratios,
            warnings=list(pack["warnings"]) if pack else [],
            reduced_verification=bool(report.get("reduced_verification", False)),
            stale=bool(stale_row[0]) if stale_row else False,
            jobs=[m.JobOut(stage=s, status=st, attempts=a, error_code=e) for s, st, a, e in job_rows],
            extraction=extraction_view(report, pack),
        )  # fmt: skip

    @app.get("/reports/{report_id}/commentary", response_model=m.CommentaryOut)
    def get_commentary(report_id: int, conn: psycopg.Connection = db) -> m.CommentaryOut:
        doc_row(conn, report_id)
        row = conn.execute(
            "SELECT id, output, stale, model_id, prompt_version, validation FROM commentaries "
            "WHERE document_id = %s ORDER BY id DESC LIMIT 1",
            (report_id,),
        ).fetchone()
        if row is None:
            raise _error(404, "commentary_not_found", "no commentary for this report yet")
        try:
            Commentary.model_validate(row[1])
        except ValidationError as exc:
            # Written by an earlier version of the contract (for example before ADR-012 added
            # `figures`): not served as current, so the screen never renders a shape it can't read.
            raise _error(
                404,
                "commentary_outdated",
                "the stored commentary was written in an older format; it is rewritten when the "
                "commentary stage runs again",
            ) from exc
        return m.CommentaryOut(
            id=row[0], output=dict(row[1]), stale=row[2], model_id=row[3], prompt_version=row[4],
            validation=dict(row[5]),
        )  # fmt: skip

    layers: OrderedDict[str, Any] = OrderedDict()  # sha256 -> text layer, most recent last
    layers_lock = threading.Lock()

    def text_layer(conn: psycopg.Connection, report_id: int) -> Any:
        """The report's text layer, kept in memory for the last few reports: the evidence panel
        asks for one page per click, and reading the cached layer from disk costs ~0.3 s."""
        assert ctx is not None
        doc = doc_row(conn, report_id)
        sha = str(doc[1])
        with layers_lock:
            if sha in layers:
                layers.move_to_end(sha)
                return layers[sha]
        layer, _ = cached_text_layer(ctx.store.path(str(doc[6])), sha, StageCache(ctx.cache_dir))
        with layers_lock:
            layers[sha] = layer
            while len(layers) > _TEXT_LAYERS_KEPT:
                layers.popitem(last=False)
        return layer

    @app.get("/reports/{report_id}/pages/{n}", response_model=m.PageOut)
    def get_page(report_id: int, n: int, conn: psycopg.Connection = db) -> m.PageOut:
        count = doc_row(conn, report_id)[3]
        if count is not None and not 1 <= n <= int(count):
            raise _error(404, "page_not_found", f"page {n} is outside 1..{count}")
        layer = text_layer(conn, report_id)
        page = next((p for p in layer.pages if p.page == n), None)
        if page is None:
            raise _error(404, "page_not_found", f"page {n} is outside 1..{layer.page_count}")
        return m.PageOut(
            page=page.page, label=page.label, width=page.width, height=page.height,
            rotation=page.rotation, text=page.text,
            words=[m.PageWord(text=w.text, bbox=w.bbox) for w in page.words],
        )  # fmt: skip

    @app.get("/reports/{report_id}/original", response_class=FileResponse)
    def get_original(report_id: int, conn: psycopg.Connection = db) -> FileResponse:
        assert ctx is not None
        doc = doc_row(conn, report_id)
        return FileResponse(
            ctx.store.path(str(doc[6])), media_type="application/pdf", filename=str(doc[2])
        )

    @app.get("/reports/{report_id}/reported-metrics", response_model=m.ReportedMetricsOut)
    def get_reported_metrics(report_id: int, conn: psycopg.Connection = db) -> m.ReportedMetricsOut:
        """A bank's own CET1 ratio and net interest margin, as stated in its narrative (OQ-4 = B).
        Found on read from the cached narrative chunks by deterministic patterns; shown "as
        reported", never used in a computation. Empty for any other document type."""
        assert ctx is not None
        doc = doc_row(conn, report_id)
        if str(doc[4]) != "bank":
            return m.ReportedMetricsOut(metrics=[], notes=[])
        pack = latest_pack(conn, report_id)[3]
        from finintel.cli.chunks_cmd import chunk_pdf

        _, _, chunks, _ = chunk_pdf(str(ctx.store.path(str(doc[6]))), ctx.cache_dir)
        offset = (
            conn.execute(
                "SELECT report->'locator'->>'folio_offset' FROM extraction_reports "
                "WHERE document_id = %s ORDER BY pack_id DESC LIMIT 1",
                (report_id,),
            ).fetchone()
            or (None,)
        )[0]
        labels = {p: str(p - int(offset)) for p in range(1, int(doc[3]) + 1)} if offset else {}
        found = find_reported_metrics(chunks, pack.get("periods", []), labels)
        return m.ReportedMetricsOut(metrics=found.metrics, notes=found.notes)

    # ------------------------------------------------------------------ review

    @app.get("/reports/{report_id}/review", response_model=m.ReviewOut)
    def get_review(report_id: int, conn: psycopg.Connection = db) -> m.ReviewOut:
        doc = doc_row(conn, report_id)
        rows = conn.execute(
            "SELECT id, item, period_id, kind, status, candidates FROM review_items "
            "WHERE document_id = %s ORDER BY id",
            (report_id,),
        ).fetchall()
        pack = conn.execute(
            "SELECT pack FROM statement_packs WHERE document_id = %s ORDER BY version DESC LIMIT 1",
            (report_id,),
        ).fetchone()
        return m.ReviewOut(
            status=str(doc[5]),
            items=[
                m.ReviewItemOut(id=r[0], item=r[1], period_id=r[2], kind=r[3], status=r[4], candidates=list(r[5]))
                for r in rows
            ],
            warnings=list(pack[0]["warnings"]) if pack else [],
        )  # fmt: skip

    def record(
        conn: psycopg.Connection,
        doc_id: int,
        action: str,
        payload: dict[str, Any],
        anchored: bool,
        reason: str | None,
    ) -> int:
        row = conn.execute(
            "INSERT INTO overrides (document_id, action, payload, anchored, reason) "
            "VALUES (%s, %s, %s::jsonb, %s, %s) RETURNING id",
            (doc_id, action, json.dumps(payload, default=str), anchored, reason),
        ).fetchone()
        assert row is not None
        return int(row[0])

    def resolve(conn: psycopg.Connection, doc_id: int, body: m.OverrideIn) -> ValueOverride:
        """Turn a request into a validated ValueOverride, or raise the 4xx the spec names."""
        if body.action == "set_null":
            if not body.reason:
                raise OverrideError(422, "reason_required", "set_null requires a reason")
            return ValueOverride(body.item, body.period_id, None, None, None, True, body.reason)
        value, raw_text, page = body.value, body.raw_text, body.page
        if body.action == "accept_candidate":
            value, raw_text, page = _candidate(conn, doc_id, body)
        if value is None or not raw_text or page is None:
            raise OverrideError(
                422, "missing_field", f"{body.action} requires value, raw_text and page"
            )
        check_value(body.item, value, raw_text)
        is_anchored = anchored_on_page(text_layer(conn, doc_id), page, raw_text)
        if not is_anchored:
            if body.action == "accept_candidate" or not body.force:
                raise OverrideError(
                    422, "unanchored_override", f"{raw_text!r} is not printed on page {page}"
                )
            if not body.reason:
                raise OverrideError(422, "reason_required", "a forced override requires a reason")
        return ValueOverride(
            body.item, body.period_id, value, raw_text, page, is_anchored, body.reason
        )

    def _candidate(
        conn: psycopg.Connection, doc_id: int, body: m.OverrideIn
    ) -> tuple[float | None, str | None, int | None]:
        if not body.candidate_id or ":" not in body.candidate_id:
            raise OverrideError(
                422, "missing_field", "accept_candidate requires candidate_id '<review item>:<n>'"
            )
        rid, _, idx = body.candidate_id.partition(":")
        row = conn.execute(
            "SELECT candidates, item, period_id FROM review_items WHERE id = %s AND document_id = %s",
            (int(rid) if rid.isdigit() else -1, doc_id),
        ).fetchone()
        candidates = list(row[0]) if row else []
        if not idx.isdigit() or int(idx) >= len(candidates):
            raise OverrideError(404, "candidate_not_found", f"no candidate {body.candidate_id}")
        assert row is not None
        # A candidate is a reading of one line in one period: it never fills another line.
        if (row[1] is not None and row[1] != body.item) or (
            row[2] is not None and row[2] != body.period_id
        ):
            raise OverrideError(
                422, "candidate_item_mismatch",
                f"candidate {body.candidate_id} is for {row[1]} {row[2]}, "
                f"not {body.item} {body.period_id}",
            )  # fmt: skip
        c = candidates[int(idx)]
        if c.get("value") is None or not c.get("raw_text") or c.get("page") is None:
            raise OverrideError(
                422, "candidate_without_value", "this candidate carries no printed value"
            )
        return float(c["value"]), str(c["raw_text"]), int(c["page"])

    @app.post("/reports/{report_id}/overrides", response_model=m.OverrideResult,
              responses={404: {}, 409: {}, 422: {}})  # fmt: skip
    def post_override(
        report_id: int, body: m.OverrideIn, conn: psycopg.Connection = db
    ) -> m.OverrideResult:
        doc = doc_row(conn, report_id)
        count = doc[3]
        if body.page is not None and not (1 <= body.page <= int(count or body.page)):
            # Checked before anything is written: a page outside the document was a 500 (the pack
            # schema refused it) or, above the last page, a figure citing a page that isn't there.
            raise _error(
                422, "page_out_of_range", f"page {body.page} is outside 1..{count} for this report"
            )
        try:
            ov = resolve(conn, report_id, body)
            with conn.transaction():
                _, version, _, pack = latest_pack(conn, report_id)
                new_pack = apply_value_override(pack, ov)
                errors = validate_pack(new_pack)
                if errors:
                    raise OverrideError(500, "pack_invalid_after_override", "; ".join(errors[:3]))
                entry = next(
                    v for v in pack["items"][ov.item]["values"] if v["period_id"] == ov.period_id
                )
                payload = {
                    "item": ov.item, "period_id": ov.period_id, "value": ov.value,
                    "raw_text": ov.raw_text, "page": ov.page, "candidate_id": body.candidate_id,
                    "before": {k: entry.get(k) for k in ("value", "raw_text", "page", "engine")},
                    "after": {"value": ov.value, "raw_text": ov.raw_text, "page": ov.page},
                }  # fmt: skip
                override_id = record(conn, report_id, body.action, payload, ov.anchored, ov.reason)
                sha = pack_sha256(new_pack)
                new_id = persist.store_pack(conn, report_id, new_pack, sha, "override")
                ratios = compute_ratios(new_pack)
                persist.store_ratio_pack(conn, new_id, ratio_pack_json(ratios))
                conn.execute(
                    "UPDATE commentaries SET stale = true WHERE document_id = %s", (report_id,)
                )
        except OverrideError as exc:
            raise _error(exc.status, exc.code, exc.message) from exc
        codes = [w["code"] for w in new_pack["warnings"] if w["code"].startswith("human_override")]
        return m.OverrideResult(
            override_id=override_id, anchored=ov.anchored, pack_version=version + 1, pack_sha=sha,
            ratios_recomputed=True, stale=True, warning_codes=sorted(set(codes)),
        )  # fmt: skip

    @app.get("/reports/{report_id}/overrides", response_model=list[m.OverrideOut])
    def list_overrides(report_id: int, conn: psycopg.Connection = db) -> list[m.OverrideOut]:
        doc_row(conn, report_id)
        rows = conn.execute(
            "SELECT id, action, anchored, reason, payload, created_at FROM overrides "
            "WHERE document_id = %s ORDER BY id",
            (report_id,),
        ).fetchall()
        return [
            m.OverrideOut(id=r[0], action=r[1], anchored=r[2], reason=r[3], payload=dict(r[4]), created_at=r[5].isoformat())
            for r in rows
        ]  # fmt: skip

    def rerun(conn: psycopg.Connection, doc_id: int, stages: tuple[str, ...]) -> m.StatusOut:
        jobs.reset(conn, doc_id, stages)
        settle(conn)
        return m.StatusOut(id=doc_id, status=str(doc_row(conn, doc_id)[5]), reran=list(stages))

    @app.post("/reports/{report_id}/unit-confirmation", response_model=m.StatusOut,
              responses={404: {}, 409: {}, 422: {}})  # fmt: skip
    def unit_confirmation(
        report_id: int, body: m.UnitConfirmationIn, conn: psycopg.Connection = db
    ) -> m.StatusOut:
        doc = doc_row(conn, report_id)
        if doc[5] != "needs_unit_confirmation":
            raise _error(409, "not_blocked", f"report is {doc[5]!r}, not waiting for a unit")
        if body.evidence_page > int(doc[3]):
            raise _error(
                422, "page_out_of_range", f"page {body.evidence_page} is outside 1..{doc[3]}"
            )
        with conn.transaction():
            record(
                conn,
                report_id,
                "unit_confirmation",
                body.model_dump(),
                True,
                f"read on p.{body.evidence_page}",
            )
        return rerun(conn, report_id, AFTER_EXTRACT)

    @app.post("/reports/{report_id}/statement-location", response_model=m.StatusOut,
              responses={404: {}, 422: {}})  # fmt: skip
    def statement_location(
        report_id: int, body: m.StatementLocationIn, conn: psycopg.Connection = db
    ) -> m.StatusOut:
        doc = doc_row(conn, report_id)
        if body.page > int(doc[3]):
            raise _error(422, "page_out_of_range", f"page {body.page} is outside 1..{doc[3]}")
        with conn.transaction():
            record(
                conn,
                report_id,
                "statement_location",
                body.model_dump(),
                True,
                f"{body.statement_type} on p.{body.page}",
            )
        return rerun(conn, report_id, AFTER_EXTRACT)

    @app.post("/reports/{report_id}/document-type", response_model=m.StatusOut,
              responses={404: {}, 409: {}, 422: {}})  # fmt: skip
    def document_type(
        report_id: int, body: m.DocumentTypeIn, conn: psycopg.Connection = db
    ) -> m.StatusOut:
        doc_row(conn, report_id)
        try:
            with conn.transaction():
                _, _, _, pack = latest_pack(conn, report_id)
                new_pack = apply_document_type(pack, body.document_type, body.reason)
                record(conn, report_id, "document_type", body.model_dump(), True, body.reason)
                persist.store_pack(conn, report_id, new_pack, pack_sha256(new_pack), "override")
                persist.set_document(conn, report_id, document_type=body.document_type)
                conn.execute(
                    "UPDATE commentaries SET stale = true WHERE document_id = %s", (report_id,)
                )
        except OverrideError as exc:
            raise _error(exc.status, exc.code, exc.message) from exc
        return rerun(conn, report_id, AFTER_TYPE)

    return app


def _worker_loop(ctx: RunContext, connect: Connect, stop: threading.Event) -> None:
    conn = connect()
    try:
        while not stop.is_set():
            if run_until_idle(conn, ctx) == 0:
                stop.wait(1.0)
    finally:
        conn.close()
