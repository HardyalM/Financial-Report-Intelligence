"""M8.2 (OQ-4 = B): the two bank ratios, exactly as CLAUDE.md defines them.

cost_to_income  = abs(operating_expenses) / total_income_after_insurance_finance
loan_to_deposit = loans_and_advances_to_customers / customer_deposits
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from finintel.contracts import validate_ratio_pack
from finintel.ratios import POINT_RATIOS, compute_ratios, ratio_pack_json
from tests.ratios.test_ratios import FULL, make_pack

BANK_LINES: dict[str, float | None] = {
    "operating_expenses": -11601.0,  # printed (11,601): the pack keeps the printed sign
    "total_income_after_insurance_finance": 18003.0,
    "total_income": 34281.0,
    "loans_and_advances_to_customers": 459857.0,
    "customer_deposits": 482745.0,
}


def bank_pack(**lines: float | None) -> dict[str, Any]:
    values = {**BANK_LINES, **lines}
    pack = make_pack()
    pack["document_type"] = "bank"
    for item, value in values.items():
        pack["items"][item] = {
            "id": item, "label_found": item, "statement": "income_statement",
            "values": [{"period_id": p["id"], "value": value, "page": 216,
                        "raw_text": None if value is None else f"{abs(value):,.0f}",
                        "confidence": 1.0, "engine": "pdfplumber"} for p in pack["periods"]],
        }  # fmt: skip
    return pack


def _ratio(pack: dict[str, Any], name: str) -> Any:
    return getattr(compute_ratios(pack).periods[0].ratios, name)


def test_cost_to_income_takes_the_magnitude_of_the_printed_expense() -> None:
    r = _ratio(bank_pack(), "cost_to_income")
    assert r.value == pytest.approx(11601 / 18003, abs=1e-15) and r.value > 0
    assert r.formula == "abs(operating_expenses) / total_income_after_insurance_finance"
    assert r.inputs["operating_expenses"].value == -11601.0  # the input keeps the printed sign


def test_loan_to_deposit() -> None:
    assert _ratio(bank_pack(), "loan_to_deposit").value == pytest.approx(459857 / 482745, abs=1e-15)


def test_no_fallback_to_total_income_when_the_insurance_line_is_absent() -> None:
    r = _ratio(bank_pack(total_income_after_insurance_finance=None), "cost_to_income")
    assert r.value is None and r.reason == "missing_input"  # never total_income instead
    assert r.missing_inputs == ["total_income_after_insurance_finance"]


def test_a_corporate_pack_has_no_bank_ratios_and_its_json_is_unchanged() -> None:
    pack = make_pack(**FULL)
    data = ratio_pack_json(compute_ratios(pack))
    for period in data["periods"]:
        assert set(period["ratios"]) == {
            "operating_margin",
            "current_ratio",
            "debt_to_equity",
            "roce",
        }
    assert "cost_to_income" not in json.dumps(data)
    assert validate_ratio_pack(data) == []


def test_a_bank_pack_has_both_and_the_corporate_four_are_not_applicable() -> None:
    data = ratio_pack_json(compute_ratios(bank_pack()))
    assert validate_ratio_pack(data) == []
    ratios = data["periods"][0]["ratios"]
    assert ratios["cost_to_income"]["applicability"] == "applicable"
    for name in ("operating_margin", "current_ratio", "debt_to_equity", "roce"):
        assert ratios[name]["applicability"] == "not_applicable" and ratios[name]["value"] is None
    assert {"cost_to_income", "loan_to_deposit"} <= POINT_RATIOS  # changes in percentage points


def test_a_profile_less_v100_pack_with_bank_lines_gets_the_bank_ratios() -> None:
    """E2 computes from the tech lead's label pack, which is v1.0.0 and carries no profile."""
    pack = bank_pack()
    pack.pop("document_type")
    assert _ratio(pack, "cost_to_income").value == pytest.approx(11601 / 18003, abs=1e-15)
