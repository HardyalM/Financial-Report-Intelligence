"""`finintel locate`: which pages hold the primary statements, and what kind of report this is.

    finintel locate company_a            human summary
    finintel locate company_a --json     the full LocateResult: locations, every candidate with
                                         its signals and rejection reason, profile, warnings

Exit codes: 0 both extracted statements found; 1 either needs review (not found or ambiguous) or
the file was refused; 2 usage; 3 held-out path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TextIO

from finintel.cache import StageCache
from finintel.cli.common import cached_text_layer, resolve_pdf
from finintel.ingest import ingest
from finintel.locate import LocateResult, StatementType, locate
from finintel.locate.models import EXTRACTED

_NAMES = {
    StatementType.INCOME_STATEMENT: "income statement",
    StatementType.BALANCE_SHEET: "balance sheet",
    StatementType.COMPREHENSIVE_INCOME: "comprehensive income",
    StatementType.CASH_FLOW: "cash flow",
    StatementType.CHANGES_IN_EQUITY: "changes in equity",
}


def locate_pdf(target: str, cache_dir: Path) -> tuple[Path, str, LocateResult]:
    """(pdf path, sha256, result) for a PDF path or fixture name. Raises on refusal."""
    pdf = resolve_pdf(target)
    record = ingest(pdf)
    layer, _ = cached_text_layer(pdf, record.sha256, StageCache(cache_dir))
    return pdf, record.sha256, locate(layer)


def as_json(pdf: Path, sha256: str, result: LocateResult) -> dict[str, Any]:
    return {"file": pdf.name, "sha256": sha256, **result.model_dump(mode="json")}


def exit_code(result: LocateResult) -> int:
    return 0 if all(result.statements[k].status == "found" for k in EXTRACTED) else 1


def report(pdf: Path, result: LocateResult, out: TextIO) -> None:
    profile = result.profile
    classified = {
        True: "balance sheet classified",
        False: "balance sheet NOT classified",
        None: "balance sheet not located",
    }[profile.balance_sheet_classified]
    folio = (
        f" · printed folio = PDF page - {result.folio_offset}"
        if result.folio_offset is not None
        else ""
    )
    print(f"{pdf.name}  {profile.document_type.value} · {classified}{folio}", file=out)
    for kind, location in result.statements.items():
        name = _NAMES[kind]
        if location.status == "not_found":
            if kind in EXTRACTED:
                print(f"  {name:22} NOT FOUND", file=out)
            continue
        pages = ", ".join(
            f"p.{p}" + (f" (printed {label})" if label else "")
            for p, label in zip(location.pages, location.page_labels, strict=True)
        )
        status = "" if location.status == "found" else f"  [{location.status.upper()}]"
        scope = location.scope.value if location.scope else "-"
        print(
            f'  {name:22} {pages}  {scope}  {location.score:.2f}  "{location.title}"{status}',
            file=out,
        )
    rejected = [c for c in result.candidates if c.excluded and c.statement_type in EXTRACTED]
    for c in rejected[:6]:
        print(f"  rejected p.{c.page} {_NAMES[c.statement_type]}: {c.excluded}", file=out)
    for warning in result.warnings:
        print(f"  warning {warning.code}: {warning.message}", file=out)


def dump_json(pdf: Path, sha256: str, result: LocateResult, out: TextIO) -> None:
    print(json.dumps(as_json(pdf, sha256, result), indent=2, ensure_ascii=False), file=out)
