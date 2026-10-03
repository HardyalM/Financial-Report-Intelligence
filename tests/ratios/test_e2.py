"""E2 end to end: pipeline pack -> ratios against the tech lead's hand-computed file."""

from __future__ import annotations

import json
from pathlib import Path

from finintel.cache import StageCache
from finintel.contracts import validate_ratio_pack
from finintel.evals import e2
from finintel.extract import extract_pack
from finintel.ratios import compute_ratios, ratio_pack_json
from scripts import gate
from tests.extract.helpers import SPEC_PATHS, run_spec, spec_data

ROOT = Path(__file__).resolve().parents[2]
EXCERPT = ROOT / "tests" / "golden" / "company_a" / "excerpt.pdf"
EXPECTED = ROOT / "fixtures" / "expected"


def test_e2_on_the_golden_excerpt_matches_all_eight_cells(tmp_path: Path) -> None:
    result = extract_pack(EXCERPT, StageCache(tmp_path))
    assert result.pack is not None
    body = e2.compare(
        result.pack,
        json.loads((EXPECTED / "company_a.json").read_text(encoding="utf-8")),
        json.loads((EXPECTED / "company_a.ratios.json").read_text(encoding="utf-8")),
    )
    assert (
        body["expected"],
        body["matched"],
        body["matched_extracted"],
        body["matched_labelled"],
    ) == (8, 8, 8, 8)
    assert validate_ratio_pack(ratio_pack_json(compute_ratios(result.pack))) == []


def test_the_m3_gate_reads_the_e2_counts(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"e2": {"expected": 8, "matched": 8}}))
    assert gate.run("M3", path)[0] == 0
    path.write_text(json.dumps({"e2": {"expected": 8, "matched": 7}}))
    assert gate.run("M3", path)[0] == 1


def test_a_wrong_expected_value_is_reported_not_absorbed(tmp_path: Path) -> None:
    result = extract_pack(EXCERPT, StageCache(tmp_path))
    assert result.pack is not None
    labels = json.loads((EXPECTED / "company_a.json").read_text(encoding="utf-8"))
    expected = json.loads((EXPECTED / "company_a.ratios.json").read_text(encoding="utf-8"))
    expected[0]["ratios"]["roce"]["value"] = 0.2  # a mistyped hand calculation
    expected[1]["ratios"]["debt_to_equity"] = {
        "value": 1.4266,
        "formula": "total_debt / total_equity",
    }
    body = e2.compare(result.pack, labels, expected)
    assert body["matched"] == 6
    bad = {
        (c["period"], c["ratio"]): c["extracted"] for c in body["cells"] if c["extracted"] != "ok"
    }
    assert "expected 0.2" in bad[("FY2024", "roce")]
    assert "expected 1.4266, computed null (missing_input)" in bad[("FY2023", "debt_to_equity")]


def test_a_bank_through_the_real_pipeline_has_four_not_applicable_ratios(tmp_path: Path) -> None:
    result = run_spec(spec_data("liquidity_ordered_bank"), tmp_path)
    assert result.pack is not None and result.pack["document_type"] == "bank"
    ratios = compute_ratios(result.pack)
    assert len(ratios.periods) == 2
    for period in ratios.periods:
        corporate = period.ratios.model_dump(
            include={"operating_margin", "current_ratio", "debt_to_equity", "roce"}
        )
        for r in corporate.values():
            assert r["value"] is None and r["reason"] == "missing_input"
            assert r["applicability"] == "not_applicable" and r["status"] == "not_applicable"
        # M8.2: the bank's own ratios. No insurance line in this bank, so no cost-to-income.
        assert period.ratios.cost_to_income is not None
        assert period.ratios.cost_to_income.reason == "missing_input"
        assert period.ratios.loan_to_deposit is not None
        assert period.ratios.loan_to_deposit.applicability == "applicable"
    assert ratios.periods[0].ratios.loan_to_deposit is not None
    assert ratios.periods[0].ratios.loan_to_deposit.value == 40000 / 42000


def test_a_spec_pack_with_a_blocked_unit_never_reaches_the_ratio_engine(tmp_path: Path) -> None:
    result = run_spec(spec_data("missing_unit"), tmp_path)
    assert result.pack is None  # no pack, so no ratios: there is nothing to compute from
    assert "missing_unit" in SPEC_PATHS


def test_e2_reads_the_bank_layout_and_matches_periods_by_end_date() -> None:
    """company_b.ratios.json: {ratios: {name: {definition, values: [{period_id, value}]}}}, with
    label periods "2024" against the pipeline's "FY2024"."""
    from finintel.evals.e2 import compare
    from tests.ratios.test_bank_ratios import bank_pack

    extracted = bank_pack()
    labelled = json.loads(json.dumps(extracted))
    labelled.pop("document_type")  # the label pack is v1.0.0
    id_of = {p["id"]: p["end_date"][:4] for p in labelled["periods"]}
    labelled["periods"] = [{**p, "id": id_of[p["id"]]} for p in labelled["periods"]]
    for item in labelled["items"].values():
        for v in item["values"]:
            v["period_id"] = id_of[v["period_id"]]
    year = next(iter(id_of.values()))
    expected = {
        "ratios": {
            "cost_to_income": {
                "definition": "abs(operating_expenses) / total_income_after_insurance_finance",
                "values": [{"period_id": year, "value": 11601 / 18003}],
            },
            "loan_to_deposit": {
                "definition": "loans_and_advances_to_customers / customer_deposits",
                "values": [{"period_id": year, "value": 459857 / 482745}],
            },
        }
    }
    out = compare(extracted, labelled, expected)
    assert (out["expected"], out["matched"]) == (2, 2), out["cells"]
    expected["ratios"]["cost_to_income"]["definition"] = "operating_expenses / total_income"
    assert compare(extracted, labelled, expected)["matched"] == 1  # a definition drift fails
