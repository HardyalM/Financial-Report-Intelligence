"""Extraction pipeline, local engines (M2.4): PDF -> StatementPack + ExtractionReport.

ingest -> text layer -> locate -> text-layer table engines -> header semantics -> mapping ->
arithmetic checks -> publish-or-null. Nothing here reads a number from a model. A blocking unit
or currency problem returns status != "ok" and no pack: there is no default and no guess.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from finintel.cache import StageCache, StageKey
from finintel.contracts import validate_pack
from finintel.ingest import ingest, score_digital_born
from finintel.llm import LLMProvider, suggest_pointers
from finintel.locate import LocateResult, locate
from finintel.locate.models import EXTRACTED, StatementType
from finintel.mapping.aliases import load_aliases
from finintel.parse.cached import cached_text_layer
from finintel.parse.engines.azure_di_engine import (
    RAW_RESPONSE_VERSION,
    AzureDiEngine,
    AzureDiError,
    normalise_layout,
    page_ranges,
)
from finintel.parse.engines.base import EngineFamily
from finintel.reconcile.pack import Assembly, EngineView, assemble
from finintel.tables import build_statement_table, statement_tables
from finintel.tables.headers import HeaderResult, read_headers
from finintel.tables.regions import statement_regions

log = structlog.get_logger(__name__)
__all__ = ["ExtractionResult", "extract_pack", "statement_tables"]
SCHEMA_CODES = {
    "missing_item", "low_confidence", "parser_disagreement", "unit_ambiguous", "sign_ambiguous",
    "multi_page_table", "restated_comparative", "alias_weak", "bank_layout", "public_sector_layout",
    "arithmetic_check_failed", "entity_scope_ambiguous", "period_ambiguous", "currency_ambiguous",
    "not_digitally_born", "lease_not_separately_presented", "derived_value", "human_override",
    "human_override_unanchored", "unit_confirmed_manually", "unclassified_balance_sheet",
    "document_type_ambiguous", "reduced_verification",
}  # fmt: skip


@dataclass
class ExtractionResult:
    status: str  # ok, needs_unit_confirmation, currency_ambiguous, statements_not_found
    pack: dict[str, Any] | None
    report: dict[str, Any]
    warnings: list[dict[str, Any]] = field(default_factory=list)
    schema_errors: list[str] = field(default_factory=list)
    located: LocateResult | None = None


def extract_pack(
    pdf: Path,
    cache: StageCache,
    *,
    engines: str = "local",
    provider: LLMProvider | None = None,
    azure: AzureDiEngine | None = None,
    location_hints: Mapping[StatementType, int] | None = None,
    confirmed_unit: tuple[str, int] | None = None,
) -> ExtractionResult:
    """`engines="all"` adds the image-layout family (Azure DI) when `azure` is configured; without
    credentials, or if the vendor call fails, it is recorded as `engine_skipped` and the local path
    carries on with a `reduced_verification` warning.

    Two human decisions can be passed in (never numbers): `location_hints` names the page of a
    statement the locator could not find or could not tell from another entity's, and
    `confirmed_unit` is a (currency, unit_scale) a person read off the page when the header was
    ambiguous. A confirmed unit is recorded on the pack as `unit_confirmed_manually`."""
    if engines not in ("local", "all"):
        raise ValueError(f"engines must be 'local' or 'all', not {engines!r}")
    record = ingest(pdf)
    layer, _ = cached_text_layer(pdf, record.sha256, cache)
    located = locate(layer, forced=location_hints)
    tables = statement_tables(pdf, record.sha256, layer, located, cache)
    notes: list[dict[str, Any]] = []
    for w in located.warnings:
        code = "missing_item" if w.code == "statement_not_found" else w.code
        if code in SCHEMA_CODES:
            notes.append({"code": code, "message": w.message, "item": None, "page": w.page})
    born = score_digital_born(layer)
    if not born.is_digitally_born:
        notes.append(
            {
                "code": "not_digitally_born",
                "message": f"{len(born.failing_pages)} of {born.pages_total} pages have "
                "too little text",
                "item": None,
                "page": None,
            }
        )
    report: dict[str, Any] = {"locator": located.model_dump(mode="json", exclude={"candidates"})}
    report["engine_skipped"] = {}
    if not tables:
        return ExtractionResult("statements_not_found", None, report, notes, located=located)
    if engines == "all":
        skipped = _add_azure(pdf, record.sha256, layer, located, tables, cache, azure)
        if skipped:
            report["engine_skipped"]["azure_di"] = skipped

    engine_names = sorted({e for by_engine in tables.values() for e in by_engine})
    headers: dict[str, HeaderResult] = {
        e: read_headers({k: by[e] for k, by in tables.items() if e in by}, layer)
        for e in engine_names
    }
    first = headers[engine_names[0]]
    if confirmed_unit is not None and any(h.status != "ok" for h in headers.values()):
        currency, scale = confirmed_unit
        first = first.model_copy(update={"status": "ok", "currency": currency, "unit_scale": scale})
        headers = {
            e: h.model_copy(update={"status": "ok", "currency": currency, "unit_scale": scale})
            for e, h in headers.items()
        }
        notes.append(
            {
                "code": "unit_confirmed_manually",
                "message": f"unit confirmed by a person: {currency} x {scale:,}",
                "item": None,
                "page": None,
            }
        )
    elif any(
        (h.status, h.currency, h.unit_scale) != (first.status, first.currency, first.unit_scale)
        for h in headers.values()
    ):
        notes.append(
            {
                "code": "parser_disagreement",
                "message": "the two text-layer engines read different units",
                "item": None,
                "page": None,
            }
        )
        return ExtractionResult("needs_unit_confirmation", None, report, notes, located=located)
    for hw in first.warnings:
        if confirmed_unit is not None and hw.code in ("unit_ambiguous", "currency_ambiguous"):
            continue  # a person has settled it
        if hw.code in SCHEMA_CODES:
            notes.append({"code": hw.code, "message": hw.message, "item": None, "page": hw.page})
    report["header"] = first.model_dump(mode="json", exclude={"tables"})
    if first.status != "ok":
        return ExtractionResult(first.status, None, report, notes, located=located)

    views = [
        EngineView(e, headers[e].tables, next(iter(headers[e].tables.values())).family)
        for e in engine_names
    ]
    if not any(v.family is EngineFamily.IMAGE_LAYOUT for v in views):
        why = report["engine_skipped"].get("azure_di", "not requested (--engines local)")
        notes.append(
            {
                "code": "reduced_verification",
                "message": f"one engine family ran (text layer); Azure DI: {why}",
                "item": None,
                "page": None,
            }
        )
    # Corporate and ambiguous ("other") documents use the corporate alias map: values stay anchored
    # and checked, and ratios are withheld for "other" (M3). A bank uses the bank map (M8.1), whose
    # lines never map to the corporate ids. NHS trusts have no map yet (OQ-5).
    doc_type = located.profile.document_type.value
    map_name = {"corporate": "corporate", "other": "corporate", "bank": "bank"}.get(doc_type)
    specs = load_aliases(map_name) if map_name else {}
    # A year left without figures on a statement says so on every line of that statement, so an
    # empty cell is never unexplained (company_c: the reason sat on the statement only).
    for hw in first.warnings:
        if hw.code == "period_ambiguous" and hw.period_id and hw.statement is not None:
            for item, spec in specs.items():
                if spec.statement is hw.statement and not spec.internal:
                    notes.append({
                        "code": "period_ambiguous", "item": item, "page": hw.page,
                        "message": f"{item} has no figure for {hw.period_id}: {hw.message}",
                    })  # fmt: skip
    assembly: Assembly = assemble(
        views,
        specs=specs,
        located=located,
        header=first,
        source={"filename": pdf.name, "page_count": record.page_count, "sha256": record.sha256},
        extra_warnings=notes,
    )
    errors = validate_pack(assembly.pack)
    report.update(assembly.report)
    report["review"] = _review_suggestions(views[0], assembly.pack, specs, provider)
    log.info(
        "extract.done",
        file=pdf.name,
        items=len(assembly.pack["items"]),
        warnings=len(assembly.pack["warnings"]),
        schema_errors=len(errors),
    )
    return ExtractionResult("ok", assembly.pack, report, assembly.pack["warnings"], errors, located)


def _review_suggestions(
    view: EngineView, pack: dict[str, Any], specs: dict[str, Any], provider: LLMProvider | None
) -> dict[str, Any]:
    """Number-blind pointers for required items with no row, review queue only (ADR-007)."""
    if provider is None:
        return {"llm": "skipped: no provider configured", "suggestions": [], "rejections": []}
    missing = [
        item
        for item, body in pack["items"].items()
        if item in specs
        and all(v["value"] is None and v.get("raw_text") is None for v in body["values"])
    ]
    suggestions, rejections = [], []
    for table in view.tables.values():
        found, rejected = suggest_pointers(table, missing, specs, provider)
        suggestions += [s.model_dump() for s in found]
        rejections += rejected
    return {"llm": provider.name, "suggestions": suggestions, "rejections": rejections}


def _add_azure(
    pdf: Path,
    sha256: str,
    layer: Any,
    located: LocateResult,
    tables: dict[Any, dict[str, Any]],
    cache: StageCache,
    azure: AzureDiEngine | None,
) -> str | None:
    """Add Azure DI tables for the located statements. Returns why it was skipped, or None."""
    if azure is None or azure.config is None:
        return "no credentials (AZURE_DI_ENDPOINT, AZURE_DI_KEY)"
    found = [located.statements[k] for k in EXTRACTED if located.statements[k].status == "found"]
    clips = {r.page: [r.bbox] for loc in found for r in statement_regions(layer, loc)}
    pages = page_ranges(clips)  # statement pages only: OQ-7 option B, about $0.08 a report
    key = StageKey.build(
        sha256, "azure_di_raw", RAW_RESPONSE_VERSION, azure.config.cache_config(pages)
    )
    try:
        raw, _ = cache.memo(
            key,
            "raw.json",
            lambda: json.dumps(
                azure.analyze_raw(pdf.read_bytes(), pages), ensure_ascii=False
            ).encode("utf-8"),
        )
    except AzureDiError as exc:
        log.warning("extract.azure_skipped", code=exc.code)
        return f"{exc.code}: {exc}"
    parsed = normalise_layout(json.loads(raw), clips=clips)
    for loc in found:
        tables[loc.statement_type]["azure_di"] = build_statement_table(layer, loc, parsed)
    return None
