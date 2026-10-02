"""EXTRACTION section 6: a withheld figure goes to review with candidates a person can accept.

Each candidate is a printed cell: its value parsed and sign-normalised exactly as it would have
been published, its raw text, page and box. A value is never computed from anything else.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from finintel.db.persist import review_rows
from finintel.tables.numbers import parse_number
from tests.extract.helpers import run_spec, spec_data, values
from tests.extract.test_rules import _extract, _perturb


def _misread(monkeypatch: pytest.MonkeyPatch, label: str, printed: str) -> None:
    """One engine reads `printed` for the row `label`: text and parsed value both, as a real
    misread would be (test_rules._perturb changes the text only)."""
    import finintel.extract as extract_module

    real = extract_module.statement_tables
    parsed = parse_number(printed)
    assert parsed is not None

    def misread(*args: Any, **kwargs: Any) -> Any:
        tables = real(*args, **kwargs)
        for by_engine in tables.values():
            table = by_engine["pymupdf_tables"]
            rows = []
            for row in table.rows:
                if row.label_text == label:
                    update = {"raw_text": printed, "parsed_value": parsed.value}
                    row = row.model_copy(
                        update={
                            "cells": {k: c.model_copy(update=update) for k, c in row.cells.items()}
                        }
                    )
                rows.append(row)
            by_engine["pymupdf_tables"] = table.model_copy(update={"rows": tuple(rows)})
        return tables

    monkeypatch.setattr(extract_module, "statement_tables", misread)


def _review(result: Any, item: str, period: str) -> dict[str, Any]:
    return next(
        r for r in result.report["review_items"] if r["item"] == item and r["period"] == period
    )


def test_an_unresolved_disagreement_lists_each_reading_with_its_printed_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _perturb(monkeypatch, "Cash and cash equivalents", "9,999")
    result = _extract(tmp_path)
    assert values(result, "cash")["FY2025"] is None
    item = _review(result, "cash", "FY2025")
    assert item["kind"] == "parser_disagreement"
    by_text = {c["raw_text"]: c for c in item["candidates"]}
    assert set(by_text) == {"900", "9,999"}
    printed = by_text["900"]
    assert printed["value"] == 900.0 and printed["engines"] == ["pdfplumber"]
    assert printed["families"] == ["text_layer"] and printed["page"] == 4
    assert len(printed["bbox"]) == 4 and printed["label"] == "Cash and cash equivalents"


def test_a_liability_candidate_is_a_positive_magnitude_as_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _misread(monkeypatch, "Borrowings", "(9,999)")  # both borrowings rows, one engine
    result = _extract(tmp_path)
    item = _review(result, "borrowings_current", "FY2025")
    assert item["kind"] == "parser_disagreement"
    by_text = {c["raw_text"]: c["value"] for c in item["candidates"]}
    assert by_text == {"(300)": 300.0, "(9,999)": 9999.0}  # printed in brackets, stored positive


def test_a_figure_below_the_threshold_keeps_its_candidate_for_review(tmp_path: Path) -> None:
    data = spec_data("company_before_group")
    income = next(p for p in data["pages"] if p.get("statement") == "income_statement")
    for row in income["rows"]:
        if row.get("label") == "Profit before taxation":  # misprinted: the lines add to 1,450
            row["values"], row["sum_of"] = ["1,460", "1,330"], []
        if row.get("label") == "Profit for the year":
            row["sum_of"] = []
    result = run_spec(data, tmp_path)
    assert values(result, "profit_before_tax")["FY2025"] is None
    item = _review(result, "profit_before_tax", "FY2025")
    assert item["kind"] == "below_threshold"
    [candidate] = item["candidates"]
    assert (candidate["value"], candidate["raw_text"], candidate["page"]) == (1460.0, "1,460", 3)
    assert candidate["families"] == ["text_layer"] and len(candidate["bbox"]) == 4


def test_review_rows_store_extraction_candidates_once() -> None:
    candidate: dict[str, Any] = {"value": 825.0, "raw_text": "825", "page": 3, "bbox": [1, 2, 3, 4]}
    extracted: list[dict[str, Any]] = [
        {"item": "net_income", "period": "FY2025", "kind": "below_threshold",
         "candidates": [candidate], "warnings": ["..."]},
        {"item": "cash", "period": "FY2025", "kind": "parser_disagreement",
         "candidates": [candidate, {**candidate, "raw_text": "852", "value": 852.0}]},
        {"item": "revenue", "period": "FY2025", "kind": "published", "candidates": []},
    ]  # fmt: skip
    warnings: list[dict[str, Any]] = [
        {"code": "parser_disagreement", "message": "unresolved", "item": "cash", "page": 3},
        {"code": "document_type_ambiguous", "message": "unclear", "item": None, "page": None},
    ]
    rows = review_rows([], warnings, extracted)
    assert [(i, p, k, len(c)) for i, p, k, c in rows] == [
        ("net_income", "FY2025", "null_with_candidates", 1),
        ("cash", "FY2025", "disagreement", 2),  # once: the warning no longer adds a second row
        (None, None, "document_type", 1),
    ]
    assert rows[0][3][0]["value"] == 825.0
