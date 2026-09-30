"""M2.5: the image-layout family joins the vote. Azure is a stand-in shaped after the documented
response (tests/extract/fake_azure.py); no real response has been captured yet."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from evals.synthetic.render import render
from evals.synthetic.spec import load_spec
from finintel.cache import StageCache
from finintel.extract import ExtractionResult, extract_pack
from finintel.locate import locate
from finintel.parse.engines.azure_di_engine import normalise_layout
from finintel.parse.text_layer import read_text_layer
from scripts import gate
from tests.extract.fake_azure import alter, engine_for, layout_body
from tests.extract.helpers import SPEC_PATHS, warnings


@pytest.fixture
def case(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    pdf = render(load_spec(SPEC_PATHS["company_before_group"]), tmp_path / "r.pdf")
    layer = read_text_layer(pdf)
    return pdf, layout_body(layer, [3, 4])


def _run(pdf: Path, tmp_path: Path, azure: Any, engines: str = "all") -> ExtractionResult:
    return extract_pack(pdf, StageCache(tmp_path / "cache"), engines=engines, azure=azure)


def _revenue(result: ExtractionResult) -> dict[str, Any]:
    assert result.pack is not None
    return next(v for v in result.pack["items"]["revenue"]["values"] if v["period_id"] == "FY2025")


def test_normalised_layout_is_in_points_with_page_numbers(
    case: tuple[Path, dict[str, Any]],
) -> None:
    _, body = case
    parsed = normalise_layout(body)
    assert parsed.engine == "azure_di" and parsed.family.value == "image_layout"
    assert {t.page for t in parsed.tables} == {3, 4} and all(
        t.strategy == "azure_layout" for t in parsed.tables
    )
    cell = next(c for t in parsed.tables for c in t.cells if c.text == "12,500")
    assert (
        cell.bbox is not None and 380 < cell.bbox[0] < 440 and cell.bbox[2] - cell.bbox[0] > 20
    )  # pt, not inches
    assert {t.page for t in normalise_layout(body, clips={3: [(0, 0, 1, 1)]}).tables} == {3}


def test_two_families_reading_the_same_cell_raise_confidence(
    tmp_path: Path, case: tuple[Path, dict[str, Any]]
) -> None:
    pdf, body = case
    local = _run(pdf, tmp_path / "l", None, engines="local")
    both = _run(pdf, tmp_path / "b", engine_for(body))
    assert both.pack is not None and local.pack is not None
    assert both.pack["source"]["parser_engines"] == ["azure_di", "pdfplumber", "pymupdf_tables"]
    local_rev, both_rev = _revenue(local), _revenue(both)
    assert both_rev["value"] == local_rev["value"] == 12500.0
    assert both_rev["engine"] == "reconciled" and local_rev["engine"] == "pdfplumber"
    assert (local_rev["confidence"], both_rev["confidence"]) == (
        0.905,
        0.99,
    )  # 0.95 x 0.90 + 0.05; 0.95 x 1.00 + 0.05, capped
    assert "reduced_verification" not in {w["code"] for w in both.pack["warnings"]}
    assert "reduced_verification" in {w["code"] for w in local.pack["warnings"]}
    assert both.schema_errors == []


def test_every_published_value_takes_its_row_from_the_text_layer(
    tmp_path: Path, case: tuple[Path, dict[str, Any]]
) -> None:
    pdf, body = case
    result = _run(pdf, tmp_path, engine_for(body))
    published = [c for c in result.report["candidates"].values() if c["decision"] == "published"]
    assert published and all(c["row_source"] == "text_layer" for c in published)
    assert all(
        c["families"] == ["image_layout", "text_layer"] for c in published if "families" in c
    )


def test_a_corrected_number_is_unanchored_and_never_published(
    tmp_path: Path, case: tuple[Path, dict[str, Any]]
) -> None:
    pdf, body = case
    result = _run(pdf, tmp_path, engine_for(alter(body, "12,500", "12,600")))
    assert _revenue(result)["value"] == 12500.0  # the page prints 12,500
    assert _revenue(result)["confidence"] == 0.905  # Azure's cell never became a candidate
    azure_notes = result.report["table_notes"]["azure_di:income_statement"]
    assert any(
        "unanchored_candidate" in n and "'12,600'" in n and "'12,500'" in n for n in azure_notes
    )
    assert result.pack is not None and 12600.0 not in [
        v["value"] for item in result.pack["items"].values() for v in item["values"]
    ]


def test_azure_without_credentials_is_recorded_as_skipped(
    tmp_path: Path, case: tuple[Path, dict[str, Any]]
) -> None:
    pdf, _ = case
    result = _run(pdf, tmp_path, None)
    assert result.report["engine_skipped"]["azure_di"].startswith("no credentials")
    assert result.pack is not None and result.pack["source"]["parser_engines"] == [
        "pdfplumber",
        "pymupdf_tables",
    ]
    assert any("no credentials" in w["message"] for w in warnings(result, "reduced_verification"))


def test_a_vendor_failure_degrades_to_the_local_path(
    tmp_path: Path, case: tuple[Path, dict[str, Any]]
) -> None:
    pdf, _ = case
    local = _run(pdf, tmp_path / "l", None, engines="local")
    down = _run(pdf, tmp_path / "d", engine_for(401))
    assert (
        "http_error" in down.report["engine_skipped"]["azure_di"]
        and "denied" in down.report["engine_skipped"]["azure_di"]
    )
    assert _revenue(down)["value"] == _revenue(local)["value"] == 12500.0
    assert "reduced_verification" in {w["code"] for w in warnings(down, "reduced_verification")}


def test_the_raw_response_is_cached_so_a_rerun_makes_no_call(
    tmp_path: Path, case: tuple[Path, dict[str, Any]]
) -> None:
    pdf, body = case
    calls: list[str] = []
    _run(pdf, tmp_path, engine_for(body, calls))
    assert calls == ["POST", "GET"]
    calls.clear()
    _run(pdf, tmp_path, engine_for(body, calls))
    assert calls == []


def test_only_the_statement_pages_are_requested(
    tmp_path: Path, case: tuple[Path, dict[str, Any]]
) -> None:
    pdf, body = case
    urls: list[str] = []
    _run(pdf, tmp_path, engine_for(body, urls=urls))
    assert "pages=3-4" in urls[0]  # the income statement and balance sheet, not the whole report


def test_a_misplaced_azure_cell_is_unanchored_not_a_second_opinion(
    tmp_path: Path, case: tuple[Path, dict[str, Any]]
) -> None:
    """Azure reports "12,500" but places it over Gross profit's figure. The text layer prints
    "3,750" there, so the cell does not anchor and is discarded: a vendor can help find a number,
    never move one to another row (ADR-001). The published value is the printed one."""
    pdf, body = case
    wrong = json.loads(json.dumps(body))
    for table in wrong["analyzeResult"]["tables"]:
        revenue = next((c for c in table["cells"] if c["content"] == "12,500"), None)
        gross = next((c for c in table["cells"] if c["content"] == "3,750"), None)
        if revenue and gross:
            revenue["boundingRegions"][0]["polygon"] = gross["boundingRegions"][0]["polygon"]
    result = _run(pdf, tmp_path, engine_for(wrong))
    assert _revenue(result)["value"] == 12500.0 and _revenue(result)["confidence"] == 0.905
    notes = result.report["table_notes"]["azure_di:income_statement"]
    assert any("unanchored_candidate" in n and "'12,500'" in n and "'3,750'" in n for n in notes)


def test_the_m2_5_gate_needs_azure_to_have_run(tmp_path: Path) -> None:
    report: dict[str, Any] = {
        "azure": {"ran": False},
        "e1": {"labelled": 22, "matched": 22, "silent_wrong": 0},
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    code, lines = gate.run("M2.5", path)
    assert code == 1 and "FAIL  azure.ran == True" in lines
    report["azure"]["ran"] = True
    path.write_text(json.dumps(report))
    assert gate.run("M2.5", path)[0] == 0


def test_locate_is_unchanged_by_the_second_family(case: tuple[Path, dict[str, Any]]) -> None:
    pdf, _ = case
    assert locate(read_text_layer(pdf)).statements
