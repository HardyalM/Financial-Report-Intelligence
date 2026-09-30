"""E2 end to end: pipeline pack -> ratios against the tech lead's hand-computed file."""

from __future__ import annotations

import json
from pathlib import Path

from finintel.cache import StageCache
from finintel.contracts import validate_ratio_pack
from finintel.evals import e2
from finintel.extract import extract_pack
from finintel.ratios import compute_ratios
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
    assert validate_ratio_pack(compute_ratios(result.pack).model_dump(mode="json")) == []


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
        for r in period.ratios.model_dump().values():
            assert r["value"] is None and r["reason"] == "missing_input"
            assert r["applicability"] == "not_applicable" and r["status"] == "not_applicable"


def test_a_spec_pack_with_a_blocked_unit_never_reaches_the_ratio_engine(tmp_path: Path) -> None:
    result = run_spec(spec_data("missing_unit"), tmp_path)
    assert result.pack is None  # no pack, so no ratios: there is nothing to compute from
    assert "missing_unit" in SPEC_PATHS
