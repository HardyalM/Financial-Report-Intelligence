"""Locator behaviour on rendered reports: selection, refusal, fallbacks, profile.

Each test renders a small ad-hoc spec (the same generator as the synthetic suite), so the locator
runs on real PDF text layers. Figures are fictional; only layout matters here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from finintel.locate import DocumentType, Scope, StatementType
from tests.locate.builders import locate_spec

IS, BS, SOCI = (
    StatementType.INCOME_STATEMENT,
    StatementType.BALANCE_SHEET,
    StatementType.COMPREHENSIVE_INCOME,
)

INCOME_ROWS: list[dict[str, Any]] = [
    {"label": "Revenue", "note": "2", "values": ["500", "450"]},
    {"label": "Cost of sales", "values": ["(300)", "(270)"]},
    {"label": "Gross profit", "values": ["200", "180"]},
    {"label": "Operating profit", "note": "3", "values": ["120", "100"]},
    {"label": "Finance costs", "note": "4", "values": ["(20)", "(18)"]},
    {"label": "Profit before taxation", "values": ["100", "82"]},
    {"label": "Taxation", "note": "5", "values": ["(25)", "(20)"]},
    {"label": "Profit for the year", "values": ["75", "62"]},
]
CLASSIFIED_ROWS: list[dict[str, Any]] = [
    {"label": "Non-current assets", "style": "section"},
    {"label": "Property, plant and equipment", "note": "6", "values": ["400", "380"]},
    {"label": "Current assets", "style": "section"},
    {"label": "Inventories", "note": "7", "values": ["90", "80"]},
    {"label": "Trade and other receivables", "note": "8", "values": ["60", "55"]},
    {"label": "Cash and cash equivalents", "values": ["50", "45"]},
    {"id": "ca", "style": "subtotal", "values": ["200", "180"]},
    {"label": "Total assets", "values": ["600", "560"]},
    {"label": "Current liabilities", "style": "section"},
    {"label": "Trade and other payables", "note": "9", "values": ["(150)", "(140)"]},
    {"id": "cl", "style": "subtotal", "values": ["(150)", "(140)"]},
    {"label": "Net assets", "values": ["450", "420"]},
    {"label": "Total equity", "values": ["450", "420"]},
]


def _statement(
    kind: str, title: str | None, rows: list[dict[str, Any]], **extra: Any
) -> dict[str, Any]:
    return {"kind": "statement", "statement": kind, "title": title, "rows": rows, **extra}


def _spec(pages: list[dict[str, Any]], **expect: Any) -> dict[str, Any]:
    return {
        "name": "adhoc",
        "hazard": "test",
        "description": "test",
        "pages": [{"kind": "narrative", "title": "Chair's statement"}, *pages],
        "expect": {
            "statements": {},
            "document_type": "corporate",
            "balance_sheet_classified": True,
            **expect,
        },
    }


def test_two_equal_group_candidates_are_refused_not_picked(tmp_path: Path) -> None:
    result = locate_spec(
        _spec(
            [
                _statement("income_statement", "Consolidated income statement", INCOME_ROWS),
                _statement("balance_sheet", "Consolidated balance sheet", CLASSIFIED_ROWS),
                _statement("balance_sheet", "Consolidated balance sheet", CLASSIFIED_ROWS),
            ]
        ),
        tmp_path,
    )
    location = result.location(BS)
    assert location.status == "ambiguous" and location.pages == (3, 4)
    [warning] = [w for w in result.warnings if w.code == "entity_scope_ambiguous"]
    assert "p.3" in warning.message and "p.4" in warning.message and "review" in warning.message


def test_only_company_statements_means_not_found_with_reasons(tmp_path: Path) -> None:
    result = locate_spec(
        _spec(
            [
                _statement("income_statement", "Consolidated income statement", INCOME_ROWS),
                _statement("balance_sheet", "Company balance sheet", CLASSIFIED_ROWS),
            ]
        ),
        tmp_path,
    )
    assert result.location(BS).status == "not_found"
    [warning] = [w for w in result.warnings if w.code == "statement_not_found"]
    assert "p.3 company-only statement" in warning.message
    assert "Point to the page" in warning.message
    assert result.profile.balance_sheet_classified is None
    assert result.profile.document_type is DocumentType.OTHER


def test_nothing_at_all_says_where_it_looked(tmp_path: Path) -> None:
    result = locate_spec(_spec([]), tmp_path)
    messages = [w.message for w in result.warnings if w.code == "statement_not_found"]
    assert len(messages) == 2
    assert all("no page carries its title, bookmark or contents entry" in m for m in messages)


def test_excluded_page_loses_to_the_real_statement(tmp_path: Path) -> None:
    result = locate_spec(
        _spec(
            [
                _statement(
                    "income_statement",
                    "Consolidated income statement",
                    INCOME_ROWS,
                    header="Five-year summary",
                ),
                _statement("income_statement", "Consolidated income statement", INCOME_ROWS),
                _statement("balance_sheet", "Consolidated balance sheet", CLASSIFIED_ROWS),
            ]
        ),
        tmp_path,
    )
    assert result.location(IS).pages == (3,)
    rejected = [c for c in result.candidates if c.page == 2 and c.statement_type is IS]
    assert rejected[0].excluded is not None and rejected[0].excluded.startswith(
        "multi-year summary"
    )


def test_comprehensive_income_stands_in_when_there_is_no_income_statement(tmp_path: Path) -> None:
    result = locate_spec(
        _spec(
            [
                _statement(
                    "comprehensive_income",
                    "Consolidated statement of comprehensive income",
                    INCOME_ROWS,
                ),
                _statement(
                    "balance_sheet", "Consolidated statement of financial position", CLASSIFIED_ROWS
                ),
            ]
        ),
        tmp_path,
    )
    location = result.location(IS)
    assert location.status == "found" and location.pages == (2,)
    assert location.source_type is SOCI
    assert [w.code for w in result.warnings if w.statement is IS] == [
        "income_statement_from_comprehensive_income"
    ]


def test_no_entity_names_anywhere_is_a_single_entity(tmp_path: Path) -> None:
    result = locate_spec(
        _spec(
            [
                _statement("income_statement", "Income statement", INCOME_ROWS),
                _statement("balance_sheet", "Statement of financial position", CLASSIFIED_ROWS),
            ]
        ),
        tmp_path,
    )
    assert result.location(IS).scope is Scope.SINGLE_ENTITY
    assert result.location(BS).scope is Scope.SINGLE_ENTITY


def test_an_unnamed_page_is_not_trusted_when_the_report_names_entities(tmp_path: Path) -> None:
    result = locate_spec(
        _spec(
            [
                _statement("income_statement", "Consolidated income statement", INCOME_ROWS),
                _statement("balance_sheet", "Balance sheet", CLASSIFIED_ROWS),
            ]
        ),
        tmp_path,
    )
    assert result.location(BS).status == "not_found"
    [candidate] = [c for c in result.candidates if c.statement_type is BS]
    assert candidate.excluded == "names no entity, but the report has group or company pages"


def test_group_and_company_columns_are_a_mixed_page(tmp_path: Path) -> None:
    result = locate_spec(
        _spec(
            [
                _statement("income_statement", "Consolidated income statement", INCOME_ROWS),
                _statement(
                    "balance_sheet",
                    "Balance sheets",
                    CLASSIFIED_ROWS,
                    columns=[
                        {"period": "2025", "entity": "Group"},
                        {"period": "2025", "entity": "Company"},
                    ],
                ),
            ]
        ),
        tmp_path,
    )
    location = result.location(BS)
    assert location.status == "found" and location.scope is Scope.MIXED


def test_a_new_statement_title_ends_a_continuation(tmp_path: Path) -> None:
    result = locate_spec(
        _spec(
            [
                _statement("income_statement", "Consolidated income statement", INCOME_ROWS),
                _statement("balance_sheet", "Consolidated balance sheet", CLASSIFIED_ROWS),
                _statement("cash_flow", "Consolidated cash flow statement", INCOME_ROWS),
            ]
        ),
        tmp_path,
    )
    assert result.location(BS).pages == (3,)
    assert not [w for w in result.warnings if w.code == "multi_page_table"]


def test_customer_deposits_alone_do_not_make_a_bank(tmp_path: Path) -> None:
    rows = [
        *CLASSIFIED_ROWS[:9],
        {"label": "Customer deposits", "values": ["(40)", "(35)"]},
        *CLASSIFIED_ROWS[9:],
    ]
    result = locate_spec(
        _spec(
            [
                _statement("income_statement", "Consolidated income statement", INCOME_ROWS),
                _statement("balance_sheet", "Consolidated balance sheet", rows),
            ]
        ),
        tmp_path,
    )
    assert result.profile.document_type is DocumentType.CORPORATE


def test_a_retailer_with_a_bank_is_ambiguous(tmp_path: Path) -> None:
    rows = [
        *CLASSIFIED_ROWS[:2],
        {"label": "Loans and advances to customers", "values": ["900", "850"]},
        *CLASSIFIED_ROWS[2:],
    ]
    result = locate_spec(
        _spec(
            [
                _statement("income_statement", "Consolidated income statement", INCOME_ROWS),
                _statement("balance_sheet", "Consolidated balance sheet", rows),
            ]
        ),
        tmp_path,
    )
    assert result.profile.document_type is DocumentType.OTHER
    assert result.profile.balance_sheet_classified is True
    assert "document_type_ambiguous" in [w.code for w in result.warnings]


def test_nhs_trust(tmp_path: Path) -> None:
    income: list[dict[str, Any]] = [
        {
            "label": "Operating income from patient care activities",
            "note": "3",
            "values": ["500,000", "480,000"],
        },
        {"label": "Other operating income", "note": "4", "values": ["40,000", "38,000"]},
        {"label": "Operating expenses", "note": "5", "values": ["(530,000)", "(512,000)"]},
        {"label": "Operating surplus", "values": ["10,000", "6,000"]},
    ]
    position: list[dict[str, Any]] = [
        {"label": "Non-current assets", "style": "section"},
        {"label": "Property, plant and equipment", "values": ["300,000", "290,000"]},
        {"label": "Current assets", "style": "section"},
        {"label": "Cash and cash equivalents", "values": ["20,000", "18,000"]},
        {"label": "Current liabilities", "style": "section"},
        {"label": "Trade and other payables", "values": ["(40,000)", "(38,000)"]},
        {"label": "Total assets employed", "values": ["280,000", "270,000"]},
        {"label": "Public dividend capital", "values": ["200,000", "195,000"]},
        {"label": "Total taxpayers' equity", "values": ["280,000", "270,000"]},
    ]
    result = locate_spec(
        _spec(
            [
                _statement("comprehensive_income", "Statement of comprehensive income", income),
                _statement("balance_sheet", "Statement of financial position", position),
            ],
        )
        | {"unit": "£000"},
        tmp_path,
    )
    assert result.profile.document_type is DocumentType.NHS_TRUST
    assert result.profile.balance_sheet_classified is True
    assert "public_sector_layout" in [w.code for w in result.warnings]
    assert result.location(BS).scope is Scope.SINGLE_ENTITY
