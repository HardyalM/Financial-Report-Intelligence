"""Renderer: money in each unit scale, percentages, pp changes, nulls, directions (M5.1 gate)."""

from __future__ import annotations

import pytest

from finintel.commentary.render import (
    build_ground_truth,
    render_money,
    render_multiple_change,
    render_percent_change,
    render_point_change,
    render_ratio,
    render_template,
)
from finintel.ratios import compute_ratios
from tests.commentary.builders import company_pack, truth_for


@pytest.mark.parametrize(
    ("value", "scale", "currency", "expected"),
    [
        (907.5, 1_000_000, "GBP", "£907.5m"),  # £m
        (13_900, 1_000_000, "GBP", "£13.9bn"),
        (907_500, 1_000, "GBP", "£907.5m"),  # £000
        (12.34, 1_000, "GBP", "£12.3k"),
        (950, 1, "GBP", "£950"),
        (1_234.5, 1_000_000, "USD", "$1.2bn"),  # $m
        (60_761, 1_000_000, "EUR", "€60.8bn"),
        (-4_200, 1_000_000, "GBP", "-£4.2bn"),
        (999.96, 1_000_000, "GBP", "£1.0bn"),  # rounds up across a unit, never "1000.0m"
        (0.05, 1_000_000, "GBP", "£50.0k"),
        (5, 1_000_000, "CHF", "CHF 5.0m"),
    ],
)
def test_money_by_unit_scale(value: float, scale: int, currency: str, expected: str) -> None:
    assert render_money(value, scale, currency) == expected


def test_rounding_is_half_up_on_exact_decimals() -> None:
    assert render_ratio(0.0625, "fraction") == "6.3%"  # float formatting would give 6.2%
    assert render_ratio(0.0635, "fraction") == "6.4%"
    assert render_money(0.1250, 1_000_000_000, "GBP") == "£125.0m"
    assert render_percent_change(6.55) == "+6.6%"


def test_ratios_and_changes() -> None:
    assert render_ratio(0.154704497951, "fraction") == "15.5%"
    assert render_ratio(0.76064, "multiple") == "0.76x"
    assert render_ratio(1.5449, "multiple") == "1.54x"
    assert render_point_change(0.4) == "+0.4 pp"
    assert render_point_change(-0.91) == "-0.9 pp"
    assert render_point_change(-0.04) == "0.0 pp"  # never "-0.0"
    assert render_multiple_change(0.0016) == "0.00x"
    assert render_multiple_change(-0.016) == "-0.02x"
    assert render_percent_change(-3.04) == "-3.0%"


def test_ground_truth_from_the_golden_packs() -> None:
    truth = truth_for()
    assert truth["item:revenue:FY2024"].rendered == "€60.8bn"
    assert truth["item:operating_profit:FY2024"].rendered == "€9.4bn"
    assert truth["ratio:operating_margin:FY2024"].rendered == "15.5%"
    assert truth["ratio:roce:FY2024"].rendered == "17.2%"
    assert truth["ratio:current_ratio:FY2024"].rendered == "0.76x"
    assert truth["change:ratio:operating_margin:FY2023:FY2024"].rendered == "-0.9 pp"
    assert truth["change:ratio:operating_margin:FY2023:FY2024"].direction == "down"
    assert truth["change:item:revenue:FY2023:FY2024"].rendered == "+1.9%"
    assert truth["change:item:revenue:FY2023:FY2024"].direction == "up"
    # a ratio or item placeholder carries the direction of the change into its period
    assert truth["ratio:operating_margin:FY2024"].direction == "down"
    assert truth["item:revenue:FY2024"].direction == "up"
    # the earliest period has nothing to compare with
    assert truth["ratio:operating_margin:FY2023"].direction is None


def test_null_values_render_as_unavailable_with_the_reason() -> None:
    truth = truth_for()
    entry = truth["ratio:debt_to_equity:FY2024"]  # total_debt is null for company_a (tech lead)
    assert entry.rendered is None and entry.status == "null" and entry.reason == "missing_input"
    assert entry.direction is None
    assert render_template("D/E was {{ratio:debt_to_equity:FY2024}}.", truth) == (
        "D/E was not available (missing input)."
    )
    assert truth["item:total_debt:FY2024"].rendered is None


def test_unknown_placeholders_are_left_as_written() -> None:
    assert render_template("{{ratio:ebitda_margin:FY2024}}", truth_for()) == (
        "{{ratio:ebitda_margin:FY2024}}"
    )


def test_a_pack_without_a_unit_scale_renders_no_money() -> None:
    pack = company_pack()
    pack["unit_scale"] = None
    entry = build_ground_truth(pack, compute_ratios(company_pack()))["item:revenue:FY2024"]
    assert entry.rendered is None and entry.reason == "unit_unknown"


def test_a_zero_base_percent_change_falls_back_to_the_absolute_amount() -> None:
    pack = company_pack()
    for pv in pack["items"]["revenue"]["values"]:
        if pv["period_id"] == "FY2023":
            pv["value"] = 0.0
    truth = build_ground_truth(pack, compute_ratios(pack))
    assert truth["change:item:revenue:FY2023:FY2024"].rendered == "+€60.8bn"
