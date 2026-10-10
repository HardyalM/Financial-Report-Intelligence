"""company_c regressions: an empty figure always says why, on its own line.

The held-out run (docs/RESULTS.md) left revenue and operating profit for one year empty with the
reason recorded on the statement, not the line (scored silent), and gave balance-sheet lines a
second, false reason: "no alias map for document type corporate yet"."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.extract.helpers import run_spec, spec_data, values, warnings


def _columnar(*periods_without_total: str) -> dict[str, Any]:
    data = spec_data("columnar_income_statement")
    income = next(p for p in data["pages"] if p.get("statement") == "income_statement")
    for column in income["columns"]:
        if column["period"] in periods_without_total and column["sub"] == "Total":
            column["sub"] = "Reported"  # no single Total column for that year: ambiguous
    return data


def test_an_ambiguous_year_is_explained_on_every_line_of_its_statement(tmp_path: Path) -> None:
    result = run_spec(_columnar("2024"), tmp_path)
    assert values(result, "revenue")["FY2025"] == 12500.0  # the other year is still read
    assert "FY2024" not in values(result, "revenue") or values(result, "revenue")["FY2024"] is None
    for item in ("revenue", "operating_profit", "profit_before_tax", "net_income"):
        [w, *_] = warnings(result, "period_ambiguous", item)
        assert "FY2024" in w["message"], item
    assert not warnings(result, "period_ambiguous", "total_assets")  # balance sheet unaffected


def test_a_statement_with_no_usable_year_gets_no_false_alias_map_reason(tmp_path: Path) -> None:
    result = run_spec(_columnar("2025", "2024"), tmp_path)
    assert result.pack is not None
    messages = [w["message"] for w in result.pack["warnings"]]
    assert not [m for m in messages if "no alias map" in m], messages
    [why] = [w for w in warnings(result, "missing_item", "revenue")]
    assert "no usable period" in why["message"]
