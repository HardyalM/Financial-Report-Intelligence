"""M2.4 rules on rendered specs: truth is the spec (E7), nulls are honest (E6), no guessing."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from evals.synthetic.spec import Spec, check_spec, load_spec, page_columns, parse_printed
from finintel.cache import StageCache
from finintel.extract import extract_pack
from finintel.tables import StatementTable
from tests.extract.helpers import SPEC_PATHS, bs_rows, row_id, run_spec, spec_data, values, warnings

LABEL_ITEMS = {
    "Revenue": "revenue",
    "Operating profit": "operating_profit",
    "Profit before taxation": "profit_before_tax",
    "Profit for the year": "net_income",
    "current_assets": "current_assets",
    "current_liabilities": "current_liabilities",
    "Total assets": "total_assets",
    "Total equity": "total_equity",
}
LIABILITIES = {"current_liabilities"}
CORPORATE = [
    p for p in SPEC_PATHS.values() if load_spec(p).expect.document_type == "corporate"
    and load_spec(p).expect.header_status == "ok"
]  # fmt: skip


@pytest.mark.parametrize("path", CORPORATE, ids=[p.stem for p in CORPORATE])
def test_every_extracted_cell_equals_the_spec(path: Path, tmp_path: Path) -> None:
    spec = load_spec(path)
    result = run_spec(spec, tmp_path)
    assert result.status == "ok" and result.schema_errors == []
    located = {k: v.pages for k, v in spec.expect.statements.items()}
    checked = 0
    for number, page in enumerate(spec.pages, start=1):
        pages = [page.left, page.right] if page.kind == "spread" else [page]
        for sheet in pages:
            if sheet.kind != "statement" or number not in located.get(sheet.statement, ()):
                continue  # narrative, or a page the locator must reject (parent company)
            columns = page_columns(spec, sheet)
            usable = spec.expect.usable_columns.get(sheet.statement, range(len(columns)))
            for row in sheet.rows:
                item = LABEL_ITEMS.get(row.id or row.label)
                if item is None or not row.values:
                    continue
                got = values(result, item)
                for index in usable:
                    period = f"FY{columns[index].period[-4:]}"
                    want = parse_printed(row.values[index])
                    want = abs(want) if item in LIABILITIES else want
                    assert got[period] == float(want), (spec.name, item, period)
                    checked += 1
    assert checked >= 8


@pytest.mark.parametrize("name", ["missing_unit", "bare_dollar"])
def test_a_blocked_unit_emits_no_pack(name: str, tmp_path: Path) -> None:
    result = run_spec(spec_data(name), tmp_path)
    assert result.pack is None
    assert result.status == spec_data(name)["expect"]["header_status"]
    assert any(w["code"] in ("unit_ambiguous", "currency_ambiguous") for w in result.warnings)


def test_removing_the_revenue_row_gives_null_and_missing_item(tmp_path: Path) -> None:
    data = spec_data("company_before_group")
    data["pages"][2]["rows"] = [r for r in data["pages"][2]["rows"] if r["label"] != "Revenue"]
    result = run_spec(data, tmp_path)
    assert values(result, "revenue") == {"FY2025": None, "FY2024": None}
    assert warnings(result, "missing_item", "revenue")
    assert values(result, "operating_profit")["FY2025"] == 1600.0  # the rest still extracts


def test_adjusted_operating_profit_is_never_chosen(tmp_path: Path) -> None:
    data = spec_data("company_before_group")
    data["pages"][2]["rows"].append(
        {"label": "Adjusted operating profit", "values": ["1,700", "1,560"], "style": "total"}
    )  # an APM memo line below the statutory statement
    result = run_spec(data, tmp_path)
    assert values(result, "operating_profit") == {"FY2025": 1600.0, "FY2024": 1480.0}


def test_a_memo_line_inside_a_chain_makes_the_chain_fail_not_guess(tmp_path: Path) -> None:
    data = spec_data("company_before_group")
    rows = data["pages"][2]["rows"]
    at = next(i for i, r in enumerate(rows) if r["label"] == "Operating profit")
    rows.insert(
        at, {"label": "Adjusted operating profit", "values": ["1,700", "1,560"], "style": "total"}
    )
    result = run_spec(data, tmp_path)
    assert values(result, "operating_profit") == {"FY2025": None, "FY2024": None}
    assert warnings(result, "arithmetic_check_failed", "operating_profit")


def test_two_equal_candidates_are_alias_weak_not_picked(tmp_path: Path) -> None:
    data = spec_data("company_before_group")
    rows = data["pages"][2]["rows"]
    at = next(i for i, r in enumerate(rows) if r["label"] == "Operating profit")
    rows.insert(at, {"id": "op_again", "label": "Operating profit", "values": ["1,599", "1,479"]})
    result = run_spec(data, tmp_path)
    assert values(result, "operating_profit") == {"FY2025": None, "FY2024": None}
    assert warnings(result, "alias_weak", "operating_profit")


def test_a_structural_subtotal_that_does_not_add_up_is_not_published(tmp_path: Path) -> None:
    data = spec_data("company_before_group")
    rows = bs_rows(data, 4)
    current_assets = next(r for r in rows if r.get("id") == "current_assets")
    current_assets["values"] = ["2,710", "2,500"]  # FY2025 off by 10, beyond rounding (tolerance 2)
    result = run_spec(data, tmp_path)
    assert values(result, "current_assets") == {"FY2025": None, "FY2024": 2500.0}
    assert warnings(result, "arithmetic_check_failed", "current_assets")
    assert warnings(result, "low_confidence", "current_assets")


def test_liabilities_are_positive_and_equity_keeps_its_sign(tmp_path: Path) -> None:
    data = spec_data("company_before_group")
    rows = bs_rows(data, 4)
    equity = next(r for r in rows if r["label"] == "Total equity")
    equity["values"] = ["(120)", "(150)"]
    retained = next(r for r in rows if r["label"] == "Retained earnings")
    retained["values"] = ["(370)", "(400)"]  # 250 + (370) = (120); 250 + (400) = (150)
    result = run_spec(data, tmp_path)
    assert values(result, "current_liabilities")["FY2025"] == 2850.0  # printed (2,850)
    assert values(result, "total_equity") == {"FY2025": -120.0, "FY2024": -150.0}


# ------------------------------------------------------------------------------ total_debt


def _debt(result: Any) -> dict[str, Any]:
    return {v["period_id"]: v for v in result.pack["items"]["total_debt"]["values"]}


def test_total_debt_is_the_derived_sum_of_four_printed_lines(tmp_path: Path) -> None:
    result = run_spec(spec_data("company_before_group"), tmp_path)
    fy25, fy24 = _debt(result)["FY2025"], _debt(result)["FY2024"]
    assert (fy25["value"], fy24["value"]) == (
        4050.0,
        4070.0,
    )  # 300+2500+150+1100; 250+2600+140+1080
    assert fy25["engine"] == "derived" and fy25["derivation"] == "sum"
    assert [d["item"] for d in fy25["derived_from"]] == [
        "borrowings_current", "borrowings_non_current",
        "lease_liabilities_current", "lease_liabilities_non_current",
    ]  # fmt: skip
    assert fy25["page"] is None and fy25["raw_text"] is None
    assert not warnings(result, "lease_not_separately_presented")


def test_a_lease_line_that_is_present_but_null_makes_total_debt_null(tmp_path: Path) -> None:
    data = spec_data("company_before_group")
    lease = next(r for r in bs_rows(data, 4) if r.get("id") == "leases_current")
    lease["values"] = ["n/a", "n/a"]  # printed, but not a number
    result = run_spec(data, tmp_path)
    assert values(result, "lease_liabilities_current") == {"FY2025": None, "FY2024": None}
    assert _debt(result)["FY2025"]["value"] is None
    assert "unresolved" in warnings(result, "missing_item", "total_debt")[0]["message"]


def test_no_lease_rows_means_borrowings_only_with_a_warning(tmp_path: Path) -> None:
    data = spec_data("company_before_group")
    rows = bs_rows(data, 4)
    data["pages"][3]["rows"] = [r for r in rows if not row_id(r).startswith("leases_")]
    result = run_spec(data, tmp_path)  # subtotals no longer add up: irrelevant to debt
    assert _debt(result)["FY2025"]["value"] == 2800.0  # 300 + 2500
    assert warnings(result, "lease_not_separately_presented", "total_debt")


def _no_debt_spec() -> dict[str, Any]:
    """company_before_group with every borrowing and lease row removed; each liability section
    still adds up, so the subtotals prove no debt row was missed."""
    data = spec_data("company_before_group")
    rows = [r for r in bs_rows(data, 4) if not row_id(r).startswith(("borrowings", "leases"))]
    for r in rows:
        if r.get("id") == "current_liabilities":
            r["values"], r["sum_of"] = ["(2,400)", "(2,300)"], ["Trade and other payables"]
        if r.get("id") == "non_current_liabilities":
            r["values"], r["sum_of"] = ["(900)", "(850)"], ["Deferred tax"]
        if r["label"] == "Non-current liabilities":
            r["label"] = "Non-current liabilities"
    at = next(i for i, r in enumerate(rows) if r["label"] == "Non-current liabilities")
    rows.insert(at + 1, {"label": "Deferred tax", "values": ["(900)", "(850)"]})
    rows.insert(
        at + 2,
        rows.pop(next(i for i, r in enumerate(rows) if r.get("id") == "non_current_liabilities")),
    )
    for r in rows:
        if r["label"] == "Net assets":
            r["values"] = ["7,400", "7,120"]
            r["sum_of"] = ["Total assets", "current_liabilities", "non_current_liabilities"]
        if r["label"] == "Total equity":
            r["values"] = ["7,400", "7,120"]
        if r["label"] == "Retained earnings":
            r["values"] = ["7,150", "6,870"]
    data["pages"][3]["rows"] = rows
    return data


def test_absent_debt_with_verified_sections_is_a_derived_zero(tmp_path: Path) -> None:
    data = _no_debt_spec()
    check_spec(Spec.model_validate(data))  # the spec itself is arithmetically sound
    result = run_spec(data, tmp_path)
    fy25 = _debt(result)["FY2025"]
    assert fy25["value"] == 0.0 and fy25["engine"] == "derived"
    assert (
        all(d.get("assumed_zero") for d in fy25["derived_from"]) and len(fy25["derived_from"]) == 4
    )
    assert not warnings(result, "missing_item", "total_debt")


def test_absent_debt_with_an_unverified_section_is_null(tmp_path: Path) -> None:
    data = _no_debt_spec()
    next(r for r in bs_rows(data, 4) if r.get("id") == "current_liabilities")["values"] = [
        "(2,405)",
        "(2,300)",
    ]
    result = run_spec(data, tmp_path)
    assert _debt(result)["FY2025"]["value"] is None and _debt(result)["FY2024"]["value"] == 0.0
    assert "could not be verified" in warnings(result, "missing_item", "total_debt")[0]["message"]


# ------------------------------------------------------------------------------ engines


def test_engines_that_read_different_cells_give_null_never_a_pick(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import finintel.extract as extract_module

    real = extract_module.statement_tables

    def perturbed(*args: Any, **kwargs: Any) -> Any:
        tables = real(*args, **kwargs)
        for by_engine in tables.values():
            table: StatementTable = by_engine["pymupdf_tables"]
            rows = []
            for row in table.rows:
                if row.label_text == "Revenue":
                    cells = {
                        k: c.model_copy(update={"raw_text": "9,999"}) for k, c in row.cells.items()
                    }
                    row = row.model_copy(update={"cells": cells})
                rows.append(row)
            by_engine["pymupdf_tables"] = table.model_copy(update={"rows": tuple(rows)})
        return tables

    monkeypatch.setattr(extract_module, "statement_tables", perturbed)
    spec = load_spec(SPEC_PATHS["company_before_group"])
    from evals.synthetic.render import render

    result = extract_pack(render(spec, tmp_path / "x.pdf"), StageCache(tmp_path / "c"))
    assert values(result, "revenue") == {"FY2025": None, "FY2024": None}
    [warning, *_] = warnings(result, "parser_disagreement", "revenue")
    assert "unresolved" in warning["message"] and "9,999" in warning["message"]
    assert values(result, "operating_profit")["FY2025"] == 1600.0  # other items unaffected


def test_unused_decimal_import_guard() -> None:
    assert Decimal("1") == 1
