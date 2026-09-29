"""The locator on the labelled goldens (M2.1 gate). PDFs are git-ignored, so CI skips this.

Truth for company_a is the tech lead's fixtures/expected/company_a.json: the pages (and printed
folios) of every labelled income-statement and balance-sheet cell.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from finintel.cache import StageCache
from finintel.cli.common import cached_text_layer
from finintel.ingest import sha256_file
from finintel.locate import DocumentType, LocateResult, Scope, StatementType, locate

ROOT = Path(__file__).resolve().parents[2]
PDFS = ROOT / "fixtures" / "pdfs"
EXPECTED = ROOT / "fixtures" / "expected"


def _locate(name: str) -> LocateResult:
    pdf = PDFS / f"{name}.pdf"
    if not pdf.exists():
        pytest.skip(f"{pdf.name} not in fixtures/pdfs/ (git-ignored; PLAN section 7.1)")
    layer, _ = cached_text_layer(pdf, sha256_file(pdf), StageCache(ROOT / "artifacts" / "cache"))
    return locate(layer)


@pytest.mark.parametrize("kind", [StatementType.INCOME_STATEMENT, StatementType.BALANCE_SHEET])
def test_company_a_pages_and_folios_match_the_labels(kind: StatementType) -> None:
    result = _locate("company_a")
    labels = json.loads((EXPECTED / "company_a.json").read_text(encoding="utf-8"))
    cells = [
        v
        for item in labels["items"].values()
        if item.get("statement") == kind.value
        for v in item["values"]
        if v.get("page") is not None
    ]
    location = result.location(kind)
    assert location.status == "found" and location.scope is Scope.GROUP
    assert set(location.pages) == {c["page"] for c in cells}
    by_page = dict(zip(location.pages, location.page_labels, strict=True))
    for cell in cells:
        if cell.get("page_label"):
            assert by_page[cell["page"]] == cell["page_label"]


def test_company_a_company_pages_are_detected_and_rejected() -> None:
    result = _locate("company_a")
    company = [c for c in result.candidates if c.scope is Scope.COMPANY]
    assert company and not any(c.selected for c in company)
    assert result.profile.document_type is DocumentType.CORPORATE
    assert result.profile.balance_sheet_classified is True


def test_company_b_is_an_unclassified_bank() -> None:
    result = _locate("company_b")
    assert result.profile.document_type is DocumentType.BANK
    assert result.profile.balance_sheet_classified is False
    assert {w.code for w in result.warnings} >= {"bank_layout", "unclassified_balance_sheet"}
    parent = [c for c in result.candidates if c.scope is Scope.COMPANY]
    assert parent and not any(c.selected for c in parent)
