"""A statement printed in two side-by-side panels on one landscape page (company_c p.139: assets on
the left, liabilities and equity on the right) is read as two stacked regions, never across the
middle. Before the fix the two panels were merged row by row: each year had two columns, so every
balance-sheet figure stayed null, and a right-panel figure sat on a left-panel label."""

from __future__ import annotations

from typing import Any

import pytest

from finintel.cache import StageCache
from finintel.extract import extract_pack
from tests.tables.panel_pdf import panel_report


@pytest.fixture(scope="module")
def result(tmp_path_factory: pytest.TempPathFactory) -> Any:
    work = tmp_path_factory.mktemp("panels")
    return extract_pack(panel_report(work / "panels.pdf"), StageCache(work / "cache"))


def _values(result: Any, item: str) -> dict[str, float | None]:
    return {v["period_id"]: v["value"] for v in result.pack["items"][item]["values"]}


def test_each_panel_is_read_on_its_own_and_the_figures_are_right(result: Any) -> None:
    assert result.pack is not None
    assert _values(result, "current_assets") == {"FY2025": 150.0, "FY2024": 130.0}  # left panel
    assert _values(result, "total_assets") == {"FY2025": 650.0, "FY2024": 610.0}
    assert _values(result, "current_liabilities") == {"FY2025": 120.0, "FY2024": 110.0}  # right
    assert _values(result, "total_equity") == {"FY2025": 300.0, "FY2024": 280.0}
    assert _values(result, "revenue") == {"FY2025": 1000.0, "FY2024": 900.0}  # unaffected


def test_no_year_is_ambiguous_and_no_false_alias_map_message(result: Any) -> None:
    codes = [(w["code"], w["message"]) for w in result.pack["warnings"]]
    assert not [m for c, m in codes if c == "period_ambiguous"], codes
    assert not [m for c, m in codes if "no alias map" in m], codes


def test_a_right_panel_figure_never_sits_on_a_left_panel_label(result: Any) -> None:
    table_rows = result.report["candidates"]
    ppe = table_rows.get("total_assets:FY2025", {})
    assert ppe.get("label") == "Total assets" and ppe.get("raw_text") == "650"
    equity = table_rows.get("total_equity:FY2025", {})
    assert equity.get("label") == "Total equity" and equity.get("raw_text") == "300"
