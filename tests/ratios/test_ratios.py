"""M3 gate: the locked ratios, exactly as CLAUDE.md defines them."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from finintel.contracts import validate_ratio_pack
from finintel.ratios import FORMULAS, compute_ratios, pack_sha256, ratio_pack_json

ROOT = Path(__file__).resolve().parents[2]
LABELS = ROOT / "fixtures" / "expected" / "company_a.json"
RATIOS = ROOT / "fixtures" / "expected" / "company_a.ratios.json"
NAMES = ("operating_margin", "current_ratio", "debt_to_equity", "roce")


def make_pack(**values: Any) -> dict[str, Any]:
    """A minimal valid-shaped pack: one period, the seven locked inputs, hand-set values."""
    period = str(values.pop("period", "FY2025"))
    items = {
        name: {
            "id": name,
            "values": [
                {
                    "period_id": period,
                    "value": value,
                    "confidence": 1.0,
                    "page": 7,
                    "raw_text": "x",
                    "engine": "hand",
                }
            ],
        }
        for name, value in values.items()
        if name not in ("document_type", "classified")
    }
    pack: dict[str, Any] = {
        "schema_version": "1.1.0", "company_name": None,
        "source": {"filename": "x.pdf", "page_count": 9},
        "currency": "GBP", "unit_scale": 1_000_000,
        "periods": [{"id": period, "label": period, "end_date": f"{period[2:]}-12-31"}],
        "items": items, "warnings": [],
    }  # fmt: skip
    if "document_type" in values:
        pack["document_type"] = values["document_type"]
    if "classified" in values:
        pack["balance_sheet_classified"] = values["classified"]
    return pack


FULL = dict(
    revenue=12345.0, operating_profit=2100.0, current_assets=8000.0, current_liabilities=5200.0,
    total_assets=20000.0, total_equity=9000.0, total_debt=4500.0,
)  # fmt: skip


def ratio(pack: dict[str, Any], name: str, index: int = 0) -> Any:
    return getattr(compute_ratios(pack).periods[index].ratios, name)


# ------------------------------------------------------------------------------ definitions


def test_the_formula_strings_equal_the_ones_in_claude_md() -> None:
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    section = text.split("## Locked v1 ratio definitions")[1].split("Input definitions")[0]
    found = {
        re.sub(r"[^a-z]+", "_", label.lower()).strip("_"): formula
        for label, formula in re.findall(r"\*\*(.+?)\*\* = `(.+?)`", section)
    }
    assert found == {
        "operating_margin": FORMULAS["operating_margin"],
        "current_ratio": FORMULAS["current_ratio"],
        "debt_to_equity": FORMULAS["debt_to_equity"],
        "roce": FORMULAS["roce"],
        "cost_to_income": FORMULAS["cost_to_income"],  # M8.2: OQ-4 = B, the tech lead
        "loan_to_deposit": FORMULAS["loan_to_deposit"],
    }
    assert set(found) == set(FORMULAS)  # nothing in code that CLAUDE.md does not define
    for name in NAMES:
        assert ratio(make_pack(**FULL), name).formula == found[name]


def test_hand_calculated_values() -> None:
    pack = make_pack(**FULL)
    assert ratio(pack, "operating_margin").value == pytest.approx(2100 / 12345, abs=1e-15)
    assert ratio(pack, "current_ratio").value == pytest.approx(8000 / 5200, abs=1e-15)
    assert ratio(pack, "debt_to_equity").value == pytest.approx(4500 / 9000, abs=1e-15)
    assert ratio(pack, "roce").value == pytest.approx(
        2100 / (20000 - 5200), abs=1e-15
    )  # total assets - CL
    assert ratio(pack, "roce").inputs["total_assets"].value == 20000.0


def test_roce_uses_total_assets_less_current_liabilities_not_equity_plus_debt() -> None:
    pack = make_pack(**FULL)
    assert ratio(pack, "roce").value != pytest.approx(2100 / (9000 + 4500))


# ------------------------------------------------------------------------------ the goldens


def test_company_a_labelled_pack_matches_the_hand_calculator() -> None:
    computed = compute_ratios(json.loads(LABELS.read_text(encoding="utf-8")))
    expected = json.loads(RATIOS.read_text(encoding="utf-8"))
    checked = 0
    for period in expected:
        got = next(p for p in computed.periods if p.period_id == period["period_id"])
        for name, want in period["ratios"].items():
            r = getattr(got.ratios, name)
            if want["value"] is None:
                assert r.value is None and r.reason == want["reason"] == "missing_input"
            else:
                assert r.value == pytest.approx(want["value"], abs=1e-9)
            assert r.formula == want["formula"]
            checked += 1
    assert checked == 8
    assert validate_ratio_pack(ratio_pack_json(computed)) == []


def test_unilever_debt_to_equity_is_null_because_total_debt_is_null() -> None:
    r = ratio(json.loads(LABELS.read_text(encoding="utf-8")), "debt_to_equity")
    assert (r.value, r.reason, r.status, r.missing_inputs) == (
        None,
        "missing_input",
        "null",
        ["total_debt"],
    )
    assert r.inputs["total_equity"].value == 22555.0 and r.inputs["total_debt"].value is None


# ---------------------------------------------------------- null, zero, negative


@pytest.mark.parametrize(
    ("missing", "affected"),
    [
        ("revenue", {"operating_margin"}),
        ("current_assets", {"current_ratio"}),
        ("current_liabilities", {"current_ratio", "roce"}),
        ("total_debt", {"debt_to_equity"}),
        ("total_equity", {"debt_to_equity"}),
        ("total_assets", {"roce"}),
        ("operating_profit", {"operating_margin", "roce"}),
    ],
)
def test_a_null_input_gives_a_null_ratio_with_reason_missing_input(
    missing: str, affected: set[str]
) -> None:
    pack = make_pack(**{**FULL, missing: None})
    for name in NAMES:
        r = ratio(pack, name)
        if name in affected:
            assert r.value is None and r.reason == "missing_input" and missing in r.missing_inputs
            assert r.status == "null" and r.applicability == "applicable"
        else:
            assert r.value is not None and r.reason is None and r.missing_inputs == []


def test_an_item_absent_from_the_pack_is_a_missing_input_not_a_zero() -> None:
    pack = make_pack(**FULL)
    del pack["items"]["revenue"]
    r = ratio(pack, "operating_margin")
    assert r.value is None and r.reason == "missing_input" and r.missing_inputs == ["revenue"]


def test_zero_denominators_are_division_by_zero_not_infinity() -> None:
    cases = {
        "operating_margin": {"revenue": 0.0},
        "current_ratio": {"current_liabilities": 0.0},
        "debt_to_equity": {"total_equity": 0.0},
        "roce": {"total_assets": 5200.0},  # equals current liabilities
    }
    for name, override in cases.items():
        r = ratio(make_pack(**{**FULL, **override}), name)
        assert (r.value, r.reason, r.status) == (None, "division_by_zero", "null")


def test_negative_equity_keeps_its_value_and_adds_a_flag() -> None:
    pack = make_pack(**{**FULL, "total_equity": -3000.0})
    r = ratio(pack, "debt_to_equity")
    assert (
        r.value == pytest.approx(4500 / -3000)
        and r.flags == ["negative_denominator"]
        and r.status == "ok"
    )
    warnings = compute_ratios(pack).warnings
    assert [(w.code, w.ratio) for w in warnings] == [("negative_denominator", "debt_to_equity")]
    assert "not meaningful" in warnings[0].message and "is shown" in warnings[0].message
    assert ratio(make_pack(**FULL), "debt_to_equity").flags == []


def test_negative_operating_profit_is_a_negative_margin_not_a_null() -> None:
    assert ratio(
        make_pack(**{**FULL, "operating_profit": -500.0}), "operating_margin"
    ).value == pytest.approx(-500 / 12345)


# ------------------------------------------------------------------------------ applicability


def test_a_bank_has_four_null_not_applicable_ratios() -> None:
    bank = make_pack(
        operating_profit=None, revenue=None, current_assets=None, current_liabilities=None,
        total_assets=906_697.0, total_equity=45_888.0, total_debt=None,
        document_type="bank", classified=False,
    )  # fmt: skip
    for name in NAMES:
        r = ratio(bank, name)
        assert (
            r.value is None and r.reason == "missing_input" and r.applicability == "not_applicable"
        )
        assert r.status == "not_applicable" and r.explanation and "banks" in r.explanation


def test_bank_ratios_stay_hidden_even_if_every_input_happened_to_be_present() -> None:
    r = ratio(make_pack(**FULL, document_type="bank", classified=False), "operating_margin")
    assert r.value is None and r.reason is None and r.applicability == "not_applicable"


def test_unclassified_balance_sheet_makes_only_the_current_ratio_not_applicable() -> None:
    pack = make_pack(**FULL, document_type="corporate", classified=False)
    assert ratio(pack, "current_ratio").applicability == "not_applicable"
    assert (
        ratio(pack, "roce").applicability == "applicable" and ratio(pack, "roce").value is not None
    )


def test_an_ambiguous_document_withholds_the_ratios_it_cannot_vouch_for() -> None:
    pack = make_pack(**FULL, document_type="other", classified=True)
    assert {n: ratio(pack, n).applicability for n in NAMES} == {
        "operating_margin": "withheld", "current_ratio": "withheld",
        "debt_to_equity": "withheld", "roce": "withheld",
    }  # fmt: skip
    assert ratio(pack, "roce").status == "withheld" and ratio(pack, "roce").value is None
    assert (
        ratio(
            make_pack(**FULL, document_type="other", classified=False), "current_ratio"
        ).applicability
        == "not_applicable"
    )


# ------------------------------------------------------------------------------ provenance, changes


def test_inputs_carry_their_page_and_badges() -> None:
    pack = make_pack(**FULL)
    pack["items"]["total_debt"]["values"][0].update(engine="derived", page=None)
    pack["items"]["total_equity"]["values"][0]["engine"] = "human_override"
    pack["items"]["revenue"]["values"][0]["engine"] = "human_override_unanchored"
    assert ratio(pack, "debt_to_equity").inputs["total_debt"].badges == ["derived"]
    assert ratio(pack, "debt_to_equity").inputs["total_debt"].page is None
    assert ratio(pack, "debt_to_equity").inputs["total_equity"].badges == ["manual"]
    assert ratio(pack, "operating_margin").inputs["revenue"].badges == ["manual_unanchored"]
    assert ratio(pack, "operating_margin").inputs["operating_profit"].page == 7


def test_changes_are_percentage_points_for_margins_and_roce_absolute_for_multiples() -> None:
    labelled = json.loads(LABELS.read_text(encoding="utf-8"))
    [change] = [
        c
        for c in compute_ratios(labelled).changes
        if c.to_period_id == "FY2024" and c.from_period_id == "FY2023"
    ]
    assert change.ratios["operating_margin"].kind == "percentage_points"
    assert change.ratios["operating_margin"].value == pytest.approx(
        (0.154704497951 - 0.163713844708) * 100, abs=1e-9
    )
    assert change.ratios["roce"].value == pytest.approx(
        (0.172426443613 - 0.188527599065) * 100, abs=1e-9
    )
    assert change.ratios["current_ratio"].kind == "absolute"
    assert change.ratios["current_ratio"].value == pytest.approx(
        0.760640405802 - 0.761560386268, abs=1e-9
    )
    assert change.ratios["debt_to_equity"].value is None  # a null never changes into a number
    assert change.items["revenue"].absolute == 1157.0
    assert change.items["revenue"].percent == pytest.approx(1157 / 59604 * 100)
    assert change.items["total_debt"].absolute is None


def test_percent_change_from_a_zero_base_is_null() -> None:
    pack = make_pack(**FULL)
    pack["periods"].append({"id": "FY2024", "label": "FY2024", "end_date": "2024-12-31"})
    for name in pack["items"]:
        pack["items"][name]["values"].append(
            {
                "period_id": "FY2024",
                "value": 0.0,
                "confidence": 1.0,
                "page": 7,
                "raw_text": "0",
                "engine": "hand",
            }
        )
    [change] = compute_ratios(pack).changes
    assert change.items["revenue"].absolute == 12345.0 and change.items["revenue"].percent is None


def test_periods_are_ordered_latest_first() -> None:
    computed = compute_ratios(json.loads(LABELS.read_text(encoding="utf-8")))
    assert [p.period_id for p in computed.periods] == ["FY2024", "FY2023"]


# ------------------------------------------------------------------------------ contract


def test_output_is_valid_against_the_schema_and_deterministic() -> None:
    pack = make_pack(**FULL)
    a, b = compute_ratios(pack), compute_ratios(deepcopy(pack))
    assert a == b and a.formulas_locked is True
    assert validate_ratio_pack(ratio_pack_json(a)) == []
    assert a.statement_pack_sha == pack_sha256(pack) == pack_sha256(deepcopy(pack))
    changed = deepcopy(pack)
    changed["items"]["revenue"]["values"][0]["value"] = 1.0
    assert compute_ratios(changed).statement_pack_sha != a.statement_pack_sha


def test_the_schema_refuses_a_ratio_pack_that_unlocks_the_formulas() -> None:
    data = ratio_pack_json(compute_ratios(make_pack(**FULL)))
    data["formulas_locked"] = False
    assert validate_ratio_pack(data)


# ------------------------------------------------------------------------------ properties

amounts = st.integers(min_value=1, max_value=10**9).map(float)


@settings(max_examples=300, deadline=None)
@given(
    revenue=amounts, profit=st.integers(-(10**9), 10**9).map(float), ca=amounts, cl=amounts,
    equity=st.integers(-(10**9), 10**9).filter(bool).map(float), debt=amounts,
    extra=st.integers(min_value=1, max_value=10**9).map(float),
)  # fmt: skip
def test_multiplying_every_input_by_1000_changes_no_ratio(
    revenue: float, profit: float, ca: float, cl: float, equity: float, debt: float, extra: float
) -> None:
    """Unit scale (GBP000 against GBPm) must never change a ratio: they are scale-free."""
    base = dict(revenue=revenue, operating_profit=profit, current_assets=ca, current_liabilities=cl,
                total_assets=cl + extra, total_equity=equity, total_debt=debt)  # fmt: skip
    scaled = {k: v * 1000 for k, v in base.items()}
    a, b = compute_ratios(make_pack(**base)), compute_ratios(make_pack(**scaled))
    for name in NAMES:
        ra, rb = getattr(a.periods[0].ratios, name), getattr(b.periods[0].ratios, name)
        assert ra.value == rb.value and ra.flags == rb.flags and ra.reason == rb.reason
