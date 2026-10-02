"""Build the report-screen fixtures (M7.1): the API's responses for six reports, as JSON.

    uv run python -m tests.e2e.fixtures.build_fixtures

Every number in them comes from the real pipeline, run the way the worker runs it: extraction,
a person's decisions through `finintel.review`, the ratio engine, chunking, retrieval and the
commentary run. Where a state needs something this machine cannot run (a second engine family, a
model's row pointer) the builder uses the test stand-ins the extraction tests use
(`tests/extract/fake_azure.py`, `finintel.llm.FakeProvider`). Each response is validated against
the API's own response models before it is written.

| id | fixture             | source                                         | states it carries   |
|----|---------------------|------------------------------------------------|---------------------|
| 1  | company_a           | fixtures/pdfs/company_a.pdf + gated commentary | R2, R8, K1, K3      |
| 2  | example_states      | tests/e2e/fixtures/specs/example_states.yaml   | R1 R3-R8, K2 K3     |
| 3  | example_not_found   | the same spec without the non-current subtotal | R2 R4 R8, K3 K6     |
| 4  | liquidity_ordered_bank | evals/synthetic/specs                       | R9, K4              |
| 5  | liquidity_ordered_insurer | evals/synthetic/specs                    | R9, K5              |
| 6  | missing_unit        | evals/synthetic/specs                          | R10                 |

company_a needs the source PDF (not committed) and the M5.2 commentary artefact
(`artifacts/commentary/company_a.json`); the builder refuses to run if that artefact was written
for a different statement pack.
"""

from __future__ import annotations

import json
import sys
import tempfile
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evals.synthetic.render import render
from evals.synthetic.spec import Spec, load_spec
from finintel.api import models as m
from finintel.api.extraction_view import extraction_view
from finintel.cache import StageCache
from finintel.cli.chunks_cmd import chunk_pdf
from finintel.commentary.audit import audit_commentary
from finintel.commentary.render import build_ground_truth
from finintel.commentary.run import allowed_years, build_commentary
from finintel.contracts import validate_pack
from finintel.contracts.ratio_pack import RatioPack
from finintel.db.persist import review_rows
from finintel.extract import ExtractionResult, extract_pack
from finintel.facts import extract_facts
from finintel.ingest import ingest
from finintel.llm import FakeProvider
from finintel.locate import locate
from finintel.locate.models import DocumentType
from finintel.parse.cached import cached_text_layer
from finintel.parse.text_layer import TextLayer, read_text_layer
from finintel.ratios import compute_ratios, pack_sha256
from finintel.retrieval.embeddings import FakeEmbedder
from finintel.retrieval.pipeline import FusionOrderReranker, InMemoryIndex, retrieve_all
from finintel.review import anchored_on_page, materialise
from finintel.review.overrides import check_value
from finintel.worker.stages import BLOCKING, STAGES
from tests.extract.fake_azure import alter, engine_for, layout_body

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUT = HERE / "api"
PDFS = HERE / "pdfs"
SPECS = ROOT / "evals" / "synthetic" / "specs"
COMPANY_A_PDF = ROOT / "fixtures" / "pdfs" / "company_a.pdf"
COMPANY_A_COMMENTARY = ROOT / "artifacts" / "commentary" / "company_a.json"


@dataclass
class Case:
    id: int
    name: str
    title: str
    pdf: Path
    cache: Path
    states: tuple[str, ...]
    engines: str = "local"
    azure: Any = None
    provider: Any = None
    #: A person's decisions, as rows of the `overrides` table: (action, payload, reason, force).
    decisions: Sequence[tuple[str, dict[str, Any], str | None]] = ()
    commentary_artefact: Path | None = None
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------------- the pipeline


def _overrides(
    layer: TextLayer, decisions: Sequence[tuple[str, dict[str, Any], str | None]]
) -> list[dict[str, Any]]:
    """The rows the API would have stored: anchoring is checked on the page, never assumed."""
    rows = []
    for n, (action, payload, reason) in enumerate(decisions, start=1):
        anchored = True
        if action == "set_value":
            check_value(float(payload["value"]), str(payload["raw_text"]))
            anchored = anchored_on_page(layer, int(payload["page"]), str(payload["raw_text"]))
        if not anchored and not reason:
            raise SystemExit(f"decision {n}: an unanchored value needs a reason")
        rows.append(
            {"id": n, "action": action, "anchored": anchored, "reason": reason, "payload": payload}
        )
    return rows


def _status(result: ExtractionResult, doc_type: str | None) -> tuple[str, str | None]:
    """(document status, the stage the worker halted after) — as `extract_stage` decides."""
    if result.pack is None:
        return BLOCKING.get(result.status, "failed"), "extract"
    if result.status in BLOCKING:
        return BLOCKING[result.status], "extract"
    if doc_type in (None, "other"):
        return "needs_document_type", "extract"
    return "ready", None


def _jobs(halted_after: str | None) -> list[m.JobOut]:
    out, done = [], True
    for stage in STAGES:
        out.append(
            m.JobOut(
                stage=stage,
                status="done" if done else "queued",
                attempts=int(done),
                error_code=None,
            )
        )
        if stage == halted_after:
            done = False
    return out


def _commentary(
    case: Case,
    pdf: Path,
    layer: TextLayer,
    pack: dict[str, Any],
    ratios: RatioPack,
    doc_type: str,
    cache_dir: Path,
) -> m.CommentaryOut:
    _, _, chunks, _ = chunk_pdf(str(pdf), cache_dir)
    located = locate(layer)
    offset = located.folio_offset
    labels = (
        {p: str(p - offset) for p in range(1, layer.page_count + 1)} if offset is not None else {}
    )
    facts = extract_facts(layer, pack)
    truth = build_ground_truth(pack, ratios, facts)
    if case.commentary_artefact is not None:
        artefact = json.loads(case.commentary_artefact.read_text())
        output = artefact["output"]
        if output["statement_pack_sha"] != pack_sha256(pack):
            raise SystemExit(
                f"{case.commentary_artefact} was written for pack "
                f"{output['statement_pack_sha'][:12]}, "
                f"not {pack_sha256(pack)[:12]}: re-run the commentary first"
            )
        pre, snapshot = artefact["pre_validation"], artefact["numbers_snapshot"]
        from finintel.contracts.commentary import Commentary

        commentary = Commentary.model_validate(output)
    else:
        index = InMemoryIndex(chunks, FakeEmbedder())
        retrieved = {
            r.topic: r for r in retrieve_all(DocumentType(doc_type), index, FusionOrderReranker())
        }
        run = build_commentary(
            provider=None,
            pack=pack,
            ratios=ratios,
            chunks=chunks,
            retrieved=retrieved,
            page_labels=labels,
            facts=facts,
        )
        commentary, pre, snapshot = run.commentary, run.metrics, run.snapshot
        output = json.loads(commentary.model_dump_json())
    audit = audit_commentary(
        commentary, {c.chunk_id: c for c in chunks}, truth, allowed_years=allowed_years(pack)
    )
    return m.CommentaryOut(
        id=case.id,
        output=output,
        stale=False,
        model_id=commentary.model.model_id if commentary.model else None,
        prompt_version=commentary.prompt_version,
        validation={"audit": audit, "pre_validation": pre, "snapshot": snapshot},
    )


def build(case: Case, work: Path) -> dict[str, Any]:
    record = ingest(case.pdf)
    cache = StageCache(case.cache)
    layer, _ = cached_text_layer(case.pdf, record.sha256, cache)
    result = extract_pack(
        case.pdf, cache, engines=case.engines, azure=case.azure, provider=case.provider
    )
    located = result.located
    overrides = _overrides(layer, case.decisions)
    chosen = [o["payload"]["document_type"] for o in overrides if o["action"] == "document_type"]
    doc_type = chosen[-1] if chosen else (located.profile.document_type.value if located else None)
    status, halted_after = _status(result, doc_type)
    pack = materialise(result.pack, overrides) if result.pack is not None else None
    if pack is not None and (errors := validate_pack(pack)):
        raise SystemExit(f"{case.name}: invalid pack: {errors[:3]}")
    report: dict[str, Any] = {}
    ratios = None
    commentary = None
    if pack is not None:
        codes = {w.get("code") for w in pack.get("warnings", [])}
        report = {
            **result.report,
            "status": result.status,
            "reduced_verification": "reduced_verification" in codes,
            "warnings": pack.get("warnings", []),
        }
        if halted_after is None:
            ratio_pack = compute_ratios(pack)
            ratios = ratio_pack.model_dump(mode="json")
            commentary = _commentary(
                case, case.pdf, layer, pack, ratio_pack, str(doc_type), case.cache
            )
    out = m.ReportOut(
        id=case.id,
        sha256=record.sha256,
        filename=case.pdf.name,
        page_count=record.page_count,
        document_type=doc_type or "other",
        status=status,
        pack_version=(1 + sum(o["action"] != "document_type" for o in overrides))
        if pack is not None
        else None,
        pack_sha=pack_sha256(pack) if pack is not None else None,
        pack=pack,
        ratios=ratios,
        warnings=list(pack["warnings"]) if pack else [],
        reduced_verification=bool(report.get("reduced_verification", False)),
        stale=False,
        jobs=_jobs(halted_after),
        extraction=extraction_view(report, pack),
    )
    suggestions = result.report.get("review", {}).get("suggestions", [])
    review = m.ReviewOut(
        status=status,
        items=[
            m.ReviewItemOut(
                id=n, item=item, period_id=period, kind=kind, status="open", candidates=candidates
            )
            for n, (item, period, kind, candidates) in enumerate(
                review_rows(suggestions, pack["warnings"] if pack else []), start=1
            )
        ],
        warnings=list(pack["warnings"]) if pack else [],
    )
    return {
        "fixture": {
            "id": case.id,
            "name": case.name,
            "title": case.title,
            "states": list(case.states),
            "notes": case.notes,
        },
        "report": json.loads(out.model_dump_json()),
        "commentary": json.loads(commentary.model_dump_json()) if commentary else None,
        "review": json.loads(review.model_dump_json()),
        "overrides": [
            {
                **json.loads(
                    m.OverrideOut(
                        id=o["id"],
                        action=o["action"],
                        anchored=o["anchored"],
                        reason=o["reason"],
                        payload=o["payload"],
                        created_at="2026-10-02T09:00:00+00:00",
                    ).model_dump_json()
                )
            }
            for o in overrides
        ],
    }


# ---------------------------------------------------------------------------------- the cases


def _render(spec: Spec, work: Path) -> Path:
    """Render, then re-save without the random file /ID so the bytes (and every sha) repeat. The
    PDF is kept next to the fixtures: the evidence viewer (M7.2) serves it as the original."""
    import pymupdf

    raw = render(spec, work / f"{spec.name}.raw.pdf")
    doc = pymupdf.open(raw)
    doc.xref_set_key(-1, "ID", "null")
    PDFS.mkdir(parents=True, exist_ok=True)
    out = PDFS / f"{spec.name}.pdf"
    doc.save(out, no_new_id=True, garbage=1)
    doc.close()
    return out


def _row_id(pdf: Path, cache: Path, label: str) -> str:
    """The id of the income-statement row with this label, as the model would be shown it."""
    from finintel.ingest import sha256_file
    from finintel.tables import statement_tables

    sha = sha256_file(pdf)
    layer, _ = cached_text_layer(pdf, sha, StageCache(cache))
    tables = statement_tables(pdf, sha, layer, locate(layer), StageCache(cache))
    table = next(by["pdfplumber"] for k, by in tables.items() if k.value == "income_statement")
    return next(r.row_id for r in table.rows if r.label_text == label)


def cases(work: Path) -> list[Case]:
    states_spec = load_spec(HERE / "specs" / "example_states.yaml")
    states_pdf = _render(states_spec, work)
    layer = read_text_layer(states_pdf)
    # The image-layout stand-in reads every cell as printed, except cash for FY2025 (it reads
    # "570" for the printed "750"): that cell never anchors, so the current-assets section check
    # cannot close for FY2025 and current assets is withheld for review (R6 on the ratio input).
    body = alter(layout_body(layer, [3, 4]), "750", "570")
    revenue_row = _row_id(states_pdf, work / "cache_states", "Sales of goods")
    pointer = FakeProvider(
        {
            "pointers": {
                "revenue": {
                    "row_id": revenue_row,
                    "reason": "the first line of the income statement is sales",
                }
            }
        }
    )
    states = Case(
        id=2,
        name="example_states",
        title="Example plc (state fixture)",
        pdf=states_pdf,
        cache=work / "cache_states",
        engines="all",
        azure=engine_for(body),
        provider=pointer,
        states=("R1", "R3", "R4", "R5", "R6", "R7", "R8", "K2", "K3"),
        decisions=(
            (
                "document_type",
                {"document_type": "corporate"},
                "A retailer: the revenue line is printed as 'Sales of goods'",
            ),
            (
                "set_value",
                {
                    "item": "operating_profit",
                    "period_id": "FY2025",
                    "value": 1480.0,
                    "raw_text": "1,480",
                    "page": 3,
                },
                "Checked against the printed line",
            ),
            (
                "set_value",
                {
                    "item": "profit_before_tax",
                    "period_id": "FY2025",
                    "value": 1100.0,
                    "raw_text": "1,100",
                    "page": 3,
                },
                "The printed 1,110 is a misprint; 1,100 is from the preliminary results",
            ),
        ),
        notes=[
            "Fictional figures. The second engine family and the model pointer are the test "
            "stand-ins.",
            "A person set the document type (no revenue line was recognised, so it was unclear).",
            "operating_profit FY2025, withheld by the misprinted subtotal below it, was "
            "confirmed by a person (anchored on p.3): R4.",
            "profit_before_tax FY2025 was forced to a value not printed on p.3: R5.",
        ],
    )

    data = deepcopy(states_spec.model_dump(mode="json"))
    data["name"] = "example_not_found"
    balance = next(p for p in data["pages"] if p.get("statement") == "balance_sheet")
    balance["rows"] = [r for r in balance["rows"] if r.get("id") != "non_current_assets"]
    income = next(p for p in data["pages"] if p.get("statement") == "income_statement")
    income["rows"][0]["label"] = "Revenue"
    income["rows"][2]["sum_of"] = ["Revenue", "Cost of sales"]
    for row in income["rows"]:
        if row.get("label") == "Profit before taxation":
            row["values"] = ["1,100", "990"]
    not_found = Case(
        id=3,
        name="example_not_found",
        title="Example plc (not found)",
        pdf=_render(Spec.model_validate(data), work),
        cache=work / "cache_nf",
        states=("R2", "R3", "R4", "R8", "K2", "K3", "K6"),
        decisions=(
            (
                "set_value",
                {
                    "item": "current_assets",
                    "period_id": "FY2025",
                    "value": 2950.0,
                    "raw_text": "2,950",
                    "page": 4,
                },
                None,
            ),
        ),
        notes=[
            "No total-assets line and no non-current subtotal: total assets is not found.",
            "current_assets FY2025 confirmed by a person (anchored on p.4): the current "
            "ratio inherits the manual badge (K6).",
        ],
    )

    def synthetic(id_: int, name: str, title: str, states_: tuple[str, ...]) -> Case:
        return Case(
            id=id_,
            name=name,
            title=title,
            pdf=_render(load_spec(SPECS / f"{name}.yaml"), work),
            cache=work / f"cache_{name}",
            states=states_,
        )

    out = [
        states,
        not_found,
        synthetic(4, "liquidity_ordered_bank", "Example Bank plc", ("R9", "K4")),
        synthetic(5, "liquidity_ordered_insurer", "Example Insurance plc", ("R9", "K5")),
        synthetic(6, "missing_unit", "Example Unit plc", ("R10",)),
    ]
    if COMPANY_A_PDF.exists() and COMPANY_A_COMMENTARY.exists():
        out.insert(
            0,
            Case(
                id=1,
                name="company_a",
                title="company_a (golden report)",
                pdf=COMPANY_A_PDF,
                cache=ROOT / "artifacts" / "cache",
                states=("R2", "R8", "K1", "K3"),
                commentary_artefact=COMPANY_A_COMMENTARY,
                notes=["The golden report: local engines (one family), M5.2 gated commentary."],
            ),
        )
    else:
        print(
            "company_a: source PDF or commentary artefact missing; keeping the committed fixture",
            file=sys.stderr,
        )
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for case in cases(work):
            body = build(case, work)
            path = OUT / f"{case.name}.json"
            path.write_text(json.dumps(body, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
            r = body["report"]
            print(
                f"{case.id} {case.name}: status={r['status']} pack={str(r['pack_sha'])[:12]} "
                f"states={','.join(case.states)} bytes={path.stat().st_size}"
            )
    index = sorted(
        (
            json.loads(p.read_text())["fixture"]
            for p in OUT.glob("*.json")
            if p.name != "index.json"
        ),
        key=lambda f: f["id"],
    )
    (OUT / "index.json").write_text(json.dumps(index, indent=1) + "\n")


if __name__ == "__main__":
    main()
