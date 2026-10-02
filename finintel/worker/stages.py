"""Pipeline stages (ARCHITECTURE section 4). Each takes a connection inside the stage's transaction.

A stage reads its inputs from the database, the object store or the content-addressed cache, writes
its outputs, and returns an `Outcome`. It never marks itself done: the runner does that in the same
transaction, so outputs and completion are atomic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
import structlog

from finintel.cache import StageCache
from finintel.commentary.audit import audit_commentary
from finintel.commentary.render import build_ground_truth
from finintel.commentary.run import allowed_years, build_commentary
from finintel.contracts.ratio_pack import RatioPack
from finintel.db import persist
from finintel.db.store import PostgresIndex, store_chunks
from finintel.extract import extract_pack
from finintel.facts import extract_facts
from finintel.ingest import ingest
from finintel.locate import locate
from finintel.locate.models import DocumentType, StatementType
from finintel.narrative import CHUNKER_VERSION
from finintel.parse.cached import cached_text_layer
from finintel.ratios import compute_ratios, pack_sha256
from finintel.retrieval.pipeline import FusionOrderReranker, retrieve_all
from finintel.retrieval.queries import QUERY_SET_VERSION
from finintel.review import materialise
from finintel.worker.context import RunContext

log = structlog.get_logger(__name__)

STAGES = ("ingest", "text_layer", "extract", "ratios", "index", "commentary")
#: The failure taxonomy of the product (parse, map, unit, sign, retrieve, generate).
FAILURE_CLASS = {
    "ingest": "parse", "text_layer": "parse", "extract": "map",
    "ratios": "map", "index": "retrieve", "commentary": "generate",
}  # fmt: skip
#: Extraction statuses that stop the pipeline until a person acts (ARCHITECTURE section 4).
BLOCKING = {
    "needs_unit_confirmation": "needs_unit_confirmation",
    "currency_ambiguous": "needs_unit_confirmation",
    "statements_not_found": "failed",
}


@dataclass(frozen=True)
class Outcome:
    """`halt` is a document status that stops the pipeline after this stage (None: carry on)."""

    halt: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class Doc:
    id: int
    sha256: str
    filename: str
    storage_key: str


def load_doc(conn: psycopg.Connection, document_id: int) -> Doc:
    row = conn.execute(
        "SELECT id, sha256, filename, storage_key FROM documents WHERE id = %s", (document_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"document {document_id}")
    return Doc(*row)


def _pdf(ctx: RunContext, doc: Doc) -> Path:
    return ctx.store.path(doc.storage_key)


def _latest_pack(conn: psycopg.Connection, document_id: int) -> tuple[int, str, dict[str, Any]]:
    row = conn.execute(
        "SELECT id, pack_sha, pack FROM statement_packs WHERE document_id = %s "
        "ORDER BY version DESC LIMIT 1",
        (document_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("no statement pack for this document")
    return int(row[0]), str(row[1]), dict(row[2])


def ingest_stage(conn: psycopg.Connection, ctx: RunContext, doc: Doc) -> Outcome:
    """Re-check the stored original and record its page count. Refusals raise IngestError."""
    record = ingest(_pdf(ctx, doc))
    if record.sha256 != doc.sha256:
        raise RuntimeError("stored original does not match its content address")
    persist.set_document(conn, doc.id, page_count=record.page_count)
    return Outcome()


def text_layer_stage(conn: psycopg.Connection, ctx: RunContext, doc: Doc) -> Outcome:
    layer, hit = cached_text_layer(_pdf(ctx, doc), doc.sha256, StageCache(ctx.cache_dir))
    log.info("stage.text_layer", pages=layer.page_count, cache_hit=hit)
    return Outcome()


def load_overrides(conn: psycopg.Connection, document_id: int) -> list[dict[str, Any]]:
    """The document's override rows, oldest first, as `{id, action, anchored, reason, payload}`."""
    rows = conn.execute(
        "SELECT id, action, anchored, reason, payload FROM overrides "
        "WHERE document_id = %s ORDER BY id",
        (document_id,),
    ).fetchall()
    return [
        {"id": r[0], "action": r[1], "anchored": r[2], "reason": r[3], "payload": dict(r[4])}
        for r in rows
    ]


def _decisions(
    overrides: list[dict[str, Any]],
) -> tuple[dict[StatementType, int], tuple[str, int] | None, str | None]:
    """The latest human decisions that steer extraction: pages, a unit, a document type."""
    hints: dict[StatementType, int] = {}
    unit: tuple[str, int] | None = None
    doc_type: str | None = None
    for row in overrides:
        payload = row["payload"]
        if row["action"] == "statement_location":
            hints[StatementType(payload["statement_type"])] = int(payload["page"])
        elif row["action"] == "unit_confirmation":
            unit = (str(payload["currency"]), int(payload["unit_scale"]))
        elif row["action"] == "document_type":
            doc_type = str(payload["document_type"])
    return hints, unit, doc_type


def extract_stage(conn: psycopg.Connection, ctx: RunContext, doc: Doc) -> Outcome:
    overrides = load_overrides(conn, doc.id)
    hints, unit, chosen_type = _decisions(overrides)
    result = extract_pack(
        _pdf(ctx, doc), StageCache(ctx.cache_dir), engines=ctx.engines, azure=ctx.azure,
        provider=ctx.provider, location_hints=hints or None, confirmed_unit=unit,
    )  # fmt: skip
    located = result.located
    doc_type = chosen_type or (located.profile.document_type.value if located else None)
    persist.set_document(conn, doc.id, document_type=doc_type)
    if result.pack is None:
        return Outcome(halt=BLOCKING.get(result.status, "failed"), detail=result.status)
    pack = materialise(result.pack, overrides)  # a person's decisions survive a re-extraction
    sha = pack_sha256(pack)
    codes = {w.get("code") for w in pack.get("warnings", [])}
    report = {
        **result.report,
        "status": result.status,
        "reduced_verification": "reduced_verification" in codes,
        "warnings": pack.get("warnings", []),
    }
    pack_id = persist.store_pack(conn, doc.id, pack, sha, "override" if overrides else "extracted")
    persist.store_report(conn, doc.id, pack_id, report)
    review = result.report.get("review", {})
    persist.store_review_items(
        conn, doc.id, review.get("suggestions", []), pack.get("warnings", []),
        result.report.get("review_items", []),
    )  # fmt: skip
    if result.status in BLOCKING:
        return Outcome(halt=BLOCKING[result.status], detail=result.status)
    if doc_type in (None, "other"):
        return Outcome(halt="needs_document_type", detail="document_type_ambiguous")
    return Outcome()


def ratios_stage(conn: psycopg.Connection, ctx: RunContext, doc: Doc) -> Outcome:
    pack_id, _, pack = _latest_pack(conn, doc.id)
    ratios = compute_ratios(pack)
    persist.store_ratio_pack(conn, pack_id, ratios.model_dump(mode="json"))
    return Outcome()


def _chunks(ctx: RunContext, doc: Doc) -> list[Any]:
    from finintel.cli.chunks_cmd import chunk_pdf

    _, _, chunks, _ = chunk_pdf(str(_pdf(ctx, doc)), ctx.cache_dir)
    return chunks


def index_stage(conn: psycopg.Connection, ctx: RunContext, doc: Doc) -> Outcome:
    """Chunk the narrative and store chunks with their embeddings. Re-running replaces them."""
    chunks = _chunks(ctx, doc)
    persist.clear_chunks(conn, doc.id)
    store_chunks(conn, doc.id, chunks, ctx.embedder)
    log.info("stage.index", chunks=len(chunks), embedder=ctx.embedder.model_id)
    return Outcome()


def commentary_stage(conn: psycopg.Connection, ctx: RunContext, doc: Doc) -> Outcome:
    pack_id, _, pack = _latest_pack(conn, doc.id)
    ratio_row = conn.execute(
        "SELECT id, pack FROM ratio_packs WHERE statement_pack_id = %s ORDER BY id DESC LIMIT 1",
        (pack_id,),
    ).fetchone()
    if ratio_row is None:
        raise RuntimeError("no ratio pack for this statement pack")
    ratio_id, ratio_body = int(ratio_row[0]), dict(ratio_row[1])
    ratios = RatioPack.model_validate(ratio_body)
    type_row = conn.execute(
        "SELECT document_type FROM documents WHERE id = %s", (doc.id,)
    ).fetchone()
    assert type_row is not None
    doc_type = str(type_row[0])
    chunks = _chunks(ctx, doc)
    index = PostgresIndex(conn, doc.id, ctx.embedder)
    retrieved = {
        r.topic: r for r in retrieve_all(DocumentType(doc_type), index, FusionOrderReranker())
    }
    layer, _ = cached_text_layer(_pdf(ctx, doc), doc.sha256, StageCache(ctx.cache_dir))
    located = locate(layer)
    offset = located.folio_offset
    labels = (
        {p: str(p - offset) for p in range(1, layer.page_count + 1)} if offset is not None else {}
    )
    facts = extract_facts(layer, pack)
    run = build_commentary(
        provider=ctx.provider, pack=pack, ratios=ratios, chunks=chunks, retrieved=retrieved,
        page_labels=labels, facts=facts,
    )  # fmt: skip
    truth = build_ground_truth(pack, ratios, facts)
    audit = audit_commentary(
        run.commentary, {c.chunk_id: c for c in chunks}, truth, allowed_years=allowed_years(pack)
    )
    c = run.commentary
    persist.store_commentary(
        conn,
        document_id=doc.id,
        statement_pack_id=pack_id,
        ratio_pack_id=ratio_id,
        chunker_version=CHUNKER_VERSION,
        model_id=c.model.model_id if c.model else None,
        prompt_version=c.prompt_version,
        query_set_version=QUERY_SET_VERSION,
        retrieval_set={
            t: [[x.chunk_id, round(x.score, 6)] for x in r.chunks] for t, r in retrieved.items()
        },
        raw_output={"mode": c.mode, "fallback_reason": run.fallback_reason},
        output=json.loads(c.model_dump_json()),
        validation={"audit": audit, "pre_validation": run.metrics, "snapshot": run.snapshot},
    )
    return Outcome()


STAGE_FUNCS = {
    "ingest": ingest_stage,
    "text_layer": text_layer_stage,
    "extract": extract_stage,
    "ratios": ratios_stage,
    "index": index_stage,
    "commentary": commentary_stage,
}
