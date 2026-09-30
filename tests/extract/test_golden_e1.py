"""M2.4 gate in CI (OQ-10 = A): E1 on the committed excerpt of company_a against the tech lead's
labels. The excerpt keeps the statement and parent-company pages at their original page numbers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from finintel.cache import StageCache
from finintel.contracts import validate_pack
from finintel.evals.e1 import compare, report_json
from finintel.extract import extract_pack

ROOT = Path(__file__).resolve().parents[2]
EXCERPT = ROOT / "tests" / "golden" / "company_a" / "excerpt.pdf"
LABELS = ROOT / "fixtures" / "expected" / "company_a.json"


@pytest.fixture(scope="module")
def result(tmp_path_factory: pytest.TempPathFactory):  # type: ignore[no-untyped-def]
    return extract_pack(EXCERPT, StageCache(tmp_path_factory.mktemp("cache")))


def test_every_labelled_cell_matches(result) -> None:  # type: ignore[no-untyped-def]
    expected = json.loads(LABELS.read_text(encoding="utf-8"))
    e1 = compare(result.pack, expected, result.report)
    assert e1["labelled"] == 22
    assert (e1["matched"], e1["honest_null"], e1["silent_wrong"], e1["unit_errors"]) == (
        22,
        0,
        0,
        0,
    )
    assert report_json(e1, "company_a", "local")["e6"] == {
        "published_llm_pointer": 0,
        "published_vision_only": 0,
    }


def test_pack_is_valid_against_the_schema(result) -> None:  # type: ignore[no-untyped-def]
    assert result.status == "ok" and result.schema_errors == []
    assert validate_pack(result.pack) == []
    assert result.pack["currency"] == "EUR" and result.pack["unit_scale"] == 1_000_000
    assert result.pack["source"]["parser_engines"] == ["pdfplumber", "pymupdf_tables"]


def test_company_pages_were_rejected(result) -> None:  # type: ignore[no-untyped-def]
    pages = {
        v["page"] for item in result.pack["items"].values() for v in item["values"] if v.get("page")
    }
    assert pages == {141, 143}  # never the parent-company pages 195 and 197


def test_total_debt_is_null_and_says_why(result) -> None:  # type: ignore[no-untyped-def]
    debt = result.pack["items"]["total_debt"]["values"]
    assert [v["value"] for v in debt] == [None, None]
    [warning] = [w for w in result.pack["warnings"] if w["item"] == "total_debt"]
    assert warning["code"] == "missing_item" and "Financial liabilities" in warning["message"]
    assert "derivatives" in warning["message"]


def test_no_published_value_is_from_an_llm_or_unanchored(result) -> None:  # type: ignore[no-untyped-def]
    for item in result.pack["items"].values():
        for v in item["values"]:
            if v["value"] is not None:
                assert v["engine"] in ("pdfplumber", "pymupdf_tables", "derived")
                assert v["confidence"] >= 0.80
                assert v["engine"] == "derived" or (v["page"] and v["raw_text"])


def test_reduced_verification_is_declared(result) -> None:  # type: ignore[no-untyped-def]
    assert "reduced_verification" in {w["code"] for w in result.pack["warnings"]}
