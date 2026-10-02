"""M8.1: bank support (EXTRACTION 1.4 and 7, SCHEMA 9, OQ-4 default A, tech lead 2026-10-02).

Bank lines are extracted under their own ids and never stand in for a corporate input: total
income is not revenue, profit before tax is not operating profit, customer deposits are not
debt. Revenue, operating profit, current assets, current liabilities and total debt are null by
design, and all four corporate ratios are not applicable, with no value computed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from finintel.mapping.aliases import load_aliases
from finintel.mapping.mapper import map_item
from finintel.ratios import compute_ratios
from finintel.tables.models import RowStyle
from tests.extract.helpers import run_spec, spec_data, values, warnings

CORPORATE_INPUTS = (
    "revenue",
    "operating_profit",
    "current_assets",
    "current_liabilities",
    "total_debt",
)


def test_the_bank_map_never_maps_to_a_corporate_input() -> None:
    bank = load_aliases("bank")
    assert not set(CORPORATE_INPUTS) & set(bank)
    for spec in load_aliases("corporate").values():
        assert "total income" not in spec.include_exact  # never revenue
    assert "net interest income" in bank["net_interest_income"].include_exact
    assert "total income" in bank["total_income"].include_exact
    assert "excluding" in bank["total_equity"].exclude_any  # not "...excluding non-controlling"


def _bank(tmp_path: Path) -> Any:
    return run_spec(spec_data("liquidity_ordered_bank"), tmp_path)


def test_a_bank_is_extracted_under_its_own_ids(tmp_path: Path) -> None:
    result = _bank(tmp_path)
    assert result.pack is not None and result.pack["document_type"] == "bank"
    assert values(result, "net_interest_income") == {"FY2025": 2200.0, "FY2024": 2100.0}
    assert values(result, "total_income") == {"FY2025": 2700.0, "FY2024": 2580.0}
    assert values(result, "profit_before_tax") == {"FY2025": 1000.0, "FY2024": 950.0}
    assert values(result, "total_assets") == {"FY2025": 53000.0, "FY2024": 51300.0}
    assert values(result, "total_equity") == {"FY2025": 4000.0, "FY2024": 3900.0}
    assert values(result, "customer_deposits")["FY2025"] == 42000.0
    assert values(result, "loans_and_advances_to_customers")["FY2025"] == 40000.0


def test_corporate_inputs_are_null_by_design_for_a_bank(tmp_path: Path) -> None:
    result = _bank(tmp_path)
    for item in CORPORATE_INPUTS:
        assert set(values(result, item).values()) == {None}, item
        [why, *_] = warnings(result, "missing_item", item)
        assert "null by design for a bank" in why["message"], item
    assert "not revenue" in warnings(result, "missing_item", "revenue")[0]["message"]
    assert "not corporate debt" in warnings(result, "missing_item", "total_debt")[0]["message"]
    assert {w["code"] for w in result.pack["warnings"]} >= {
        "bank_layout",
        "unclassified_balance_sheet",
    }


def test_all_four_corporate_ratios_are_not_applicable_and_none_is_computed(tmp_path: Path) -> None:
    ratios = compute_ratios(_bank(tmp_path).pack)
    for period in ratios.periods:
        for name in ("operating_margin", "current_ratio", "debt_to_equity", "roce"):
            r = getattr(period.ratios, name)
            assert r.applicability == "not_applicable" and r.value is None, (period.period_id, name)
            assert "banks" in (r.explanation or "")


def test_the_same_figure_printed_twice_is_one_match_and_different_figures_still_tie(
    tmp_path: Path,
) -> None:
    from evals.synthetic.render import render
    from evals.synthetic.spec import Spec
    from finintel.cache import StageCache
    from finintel.ingest import sha256_file
    from finintel.locate import locate
    from finintel.parse.cached import cached_text_layer
    from finintel.tables import statement_tables

    def income_table(rows_after: list[dict[str, Any]], name: str) -> Any:
        data = spec_data("liquidity_ordered_bank")
        income = next(p for p in data["pages"] if p.get("statement") == "income_statement")
        income["rows"] += rows_after
        pdf = render(Spec.model_validate(data), tmp_path / f"{name}.pdf")
        cache = StageCache(tmp_path / f"cache_{name}")
        sha = sha256_file(pdf)
        layer, _ = cached_text_layer(pdf, sha, cache)
        tables = statement_tables(pdf, sha, layer, locate(layer), cache)
        return next(by["pdfplumber"] for k, by in tables.items() if k.value == "income_statement")

    spec = load_aliases("bank")["profit_for_the_year"]
    attribution = [
        {"label": "Profit attributable to ordinary shareholders", "values": ["700", "660"]},
        {"label": "Profit attributable to non-controlling interests", "values": ["50", "50"]},
    ]
    repeated = income_table(
        [
            *attribution,
            {"label": "Profit for the year", "style": "total", "values": ["750", "710"]},
        ],
        "same",
    )
    m = map_item(repeated, spec)
    assert m.row is not None and not m.weak
    assert m.row.row_id == next(
        r.row_id for r in repeated.rows if r.label_text == "Profit for the year"
    )
    different = income_table(
        [
            *attribution,
            {"label": "Profit for the year", "style": "total", "values": ["751", "710"]},
        ],
        "diff",
    )
    m2 = map_item(different, spec)
    totals = [r for r in different.rows if r.label_text == "Profit for the year"]
    assert len(totals) == 2 and all(r.style is RowStyle.TOTAL for r in totals)  # a real tie
    assert m2.row is None and m2.weak  # two different printed figures: no choice is made


def test_a_printed_equity_subtotal_is_not_counted_twice(tmp_path: Path) -> None:
    data = spec_data("liquidity_ordered_bank")
    balance = next(p for p in data["pages"] if p.get("statement") == "balance_sheet")
    rows = [r for r in balance["rows"] if r.get("label") != "Total equity"]
    rows += [
        {"label": "Ordinary shareholders' equity", "style": "subtotal",
         "values": ["4,000", "3,900"], "sum_of": ["Share capital", "Retained earnings"]},
        {"label": "Non-controlling interests", "values": ["200", "150"]},
        {"label": "Total equity", "style": "total", "values": ["4,200", "4,050"],
         "sum_of": ["Ordinary shareholders' equity", "Non-controlling interests"]},
    ]  # fmt: skip
    balance["rows"] = rows
    for row in balance["rows"]:  # keep the printed balance sheet consistent
        if row.get("label") == "Total liabilities":
            row["values"] = ["48,800", "47,250"]
            row["sum_of"] = []
    result = run_spec(data, tmp_path)
    assert values(result, "total_equity") == {"FY2025": 4200.0, "FY2024": 4050.0}
    assert not warnings(result, "arithmetic_check_failed", "total_equity")
