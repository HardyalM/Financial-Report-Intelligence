"""The report-screen fixtures are API responses the pipeline could have served (M7.1).

They are built by tests/e2e/fixtures/build_fixtures.py. These checks need no PDF and no network:
each response validates against the API's models and the pack and ratio schemas, the ratios are
what the ratio engine computes from the pack, and every state a fixture claims is present in the
data the screen reads.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from finintel.api import models as m
from finintel.contracts import validate_pack
from finintel.contracts.commentary import Commentary
from finintel.ratios import compute_ratios, pack_sha256

API = Path(__file__).resolve().parent / "fixtures" / "api"
NAMES = sorted(p.stem for p in API.glob("*.json") if p.name != "index.json")


def load(name: str) -> dict[str, Any]:
    body: dict[str, Any] = json.loads((API / f"{name}.json").read_text())
    return body


def test_the_index_lists_every_fixture_once() -> None:
    index = json.loads((API / "index.json").read_text())
    assert sorted(f["name"] for f in index) == NAMES
    assert [f["id"] for f in index] == sorted({f["id"] for f in index})


@pytest.mark.parametrize("name", NAMES)
def test_each_fixture_is_a_valid_api_response(name: str) -> None:
    body = load(name)
    report = m.ReportOut.model_validate(body["report"])
    m.ReviewOut.model_validate(body["review"])
    for o in body["overrides"]:
        m.OverrideOut.model_validate(o)
    if report.pack is not None:
        assert validate_pack(report.pack) == []
        assert report.pack_sha == pack_sha256(report.pack)
    if report.ratios is not None:
        assert report.pack is not None
        recomputed = compute_ratios(report.pack).model_dump(mode="json")
        assert recomputed == report.ratios  # the ratio engine, not the builder, made these
    if body["commentary"] is not None:
        out = m.CommentaryOut.model_validate(body["commentary"])
        commentary = Commentary.model_validate(out.output)
        # Stale means written for an earlier pack version; otherwise it is this pack's.
        assert (commentary.statement_pack_sha != report.pack_sha) == out.stale == report.stale


def _value(report: dict[str, Any], item: str, period: str) -> dict[str, Any]:
    values = report["pack"]["items"][item]["values"]
    return next(v for v in values if v["period_id"] == period)


def test_example_states_carries_its_row_and_card_states() -> None:
    r = load("example_states")["report"]
    p25 = "FY2025"
    families = r["extraction"]["candidates"]["total_equity:FY2025"]["families"]
    assert families == ["image_layout", "text_layer"]  # R1
    assert _value(r, "total_debt", p25)["derived_from"]  # R3
    assert _value(r, "operating_profit", p25)["engine"] == "human_override"  # R4
    assert _value(r, "profit_before_tax", p25)["engine"] == "human_override_unanchored"  # R5
    assert _value(r, "net_income", p25)["value"] is None  # R6: a withheld candidate
    assert r["extraction"]["candidates"]["net_income:FY2025"]["raw_text"] == "825"
    review = load("example_states")["review"]["items"]
    assert [(i["item"], i["kind"]) for i in review] == [("revenue", "llm_suggestion")]  # R7
    assert _value(r, "total_assets", p25)["value"] is None  # R8
    assert r["extraction"]["candidates"]["total_assets:FY2025"]["decision"] == "no_candidate"
    ratios = r["ratios"]["periods"][0]["ratios"]
    assert ratios["debt_to_equity"]["flags"] == ["negative_denominator"]  # K2
    assert ratios["operating_margin"]["reason"] == "missing_input"  # K3


def test_example_not_found_carries_a_manual_input_and_a_missing_one() -> None:
    r = load("example_not_found")["report"]
    ratios = r["ratios"]["periods"][0]["ratios"]
    assert ratios["current_ratio"]["inputs"]["current_assets"]["badges"] == ["manual"]  # K6
    assert ratios["roce"]["missing_inputs"] == ["total_assets"]  # K3 -> R8
    assert r["extraction"]["searched_for"]["total_assets"]["labels"] == ["total assets"]


def test_the_bank_insurer_and_blocked_fixtures() -> None:
    bank = load("liquidity_ordered_bank")["report"]
    assert {v["status"] for v in bank["ratios"]["periods"][0]["ratios"].values()} == {
        "not_applicable"
    }  # K4
    assert bank["pack"]["balance_sheet_classified"] is False  # R9
    insurer = load("liquidity_ordered_insurer")["report"]
    assert insurer["status"] == "needs_document_type" and insurer["ratios"] is None  # K5
    blocked = load("missing_unit")["report"]
    assert blocked["status"] == "needs_unit_confirmation" and blocked["pack"] is None  # R10


def test_the_commentary_topic_states() -> None:
    failed = load("example_failed")["commentary"]["output"]
    assert failed["mode"] == "generated"
    statuses = {t["topic"]: (t["status"], t["reason"]) for t in failed["topics"]}
    status, reason = statuses["revenue_drivers"]
    assert status == "validation_failed" and reason.startswith("1 paragraph removed: ")
    assert "it used advice language" in reason
    stale = load("example_stale")
    assert stale["commentary"]["stale"] and stale["report"]["stale"]
    assert [o["action"] for o in stale["overrides"]] == ["set_value"]
    bank = load("liquidity_ordered_bank")["commentary"]["output"]
    assert {t["status"] for t in bank["topics"]} >= {"insufficient_evidence"}
    assert load("example_states")["commentary"]["output"]["mode"] == "extractive"
