"""E3 comparison: printed-folio conversion, hit rule, report fields. No database, no PDF."""

from __future__ import annotations

import pytest

from finintel.evals import e3
from tests.retrieval.test_retrieval import _chunk


def _at(cid: str, page: int) -> object:
    c = _chunk(cid, "x")
    return c.model_copy(update={"page_start": page, "page_end": page})


def test_printed_labels_are_converted_with_the_folio_offset() -> None:
    chunks = [_at("a", 10), _at("b", 11)]
    labels = {
        "page_basis": "printed page numbers",
        "queries": [{"q": "q", "must_include_page_any_of": [7]}],
    }
    r = e3.compare(labels, chunks, lambda q: ["a"], folio_offset=3, models={"embedding": "m"})  # type: ignore[arg-type]
    assert r["hit_at_8"] == 1.0 and r["cells"][0]["expected_pdf_pages"] == [10]
    r = e3.compare(labels, chunks, lambda q: ["b"], folio_offset=3, models={})  # type: ignore[arg-type]
    assert r["hits"] == 0 and r["cells"][0]["retrieved"][0]["pdf_pages"] == [11, 11]


def test_pdf_basis_is_used_as_is_and_only_top_8_count() -> None:
    chunks = [_at(f"c{i}", i + 1) for i in range(10)]
    labels = {"queries": [{"q": "q", "must_include_page_any_of": [10]}]}
    ids = [f"c{i}" for i in range(10)]
    r = e3.compare(labels, chunks, lambda q: ids, folio_offset=None, models={})  # type: ignore[arg-type]
    assert r["hits"] == 0 and r["page_basis"] == "pdf"


def test_printed_labels_without_offset_fail_loudly() -> None:
    labels = {"page_basis": "printed", "queries": []}
    with pytest.raises(ValueError):
        e3.compare(labels, [], lambda q: [], folio_offset=None, models={})
