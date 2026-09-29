"""Raw pdfplumber dumps: cells exactly as returned, 1-based pages, order kept."""

from __future__ import annotations

from pathlib import Path

import pytest

from finintel.parse.engines.pdfplumber_engine import PdfplumberEngine
from tests.inspect.synthetic import ruled_table_pdf


def test_ruled_table_cells_are_verbatim(tmp_path: Path) -> None:
    pdf = ruled_table_pdf(tmp_path / "ruled.pdf")
    [page] = PdfplumberEngine().raw_tables(pdf, [1])
    assert page.page == 1 and page.error is None
    [table] = [t for t in page.tables if t.strategy == "lines"]
    assert table.rows == (
        ("Item", "2025", "2024"),
        ("Revenue", "13,907.5", "12,345.0"),
        ("Borrowings", "(250.0)", "\u2013"),
    )
    assert table.bbox == (50.0, 100.0, 450.0, 160.0)
    assert [len(r) for r in table.cell_bboxes] == [len(r) for r in table.rows]
    assert table.cell_bboxes[1][1] == (250.0, 120.0, 350.0, 140.0)


def test_text_strategy_finds_the_unruled_statement(mini_pdf: Path) -> None:
    [page] = PdfplumberEngine().raw_tables(mini_pdf, [3])
    text_tables = [t for t in page.tables if t.strategy == "text"]
    rows = [row for t in text_tables for row in t.rows]
    revenue = [row for row in rows if row and row[0] == "Revenue"]
    assert revenue and "13,907.5" in revenue[0] and "12,345.0" in revenue[0]
    assert page.count("text") == len(text_tables)


def test_pages_keep_request_order(mini_pdf: Path) -> None:
    pages = PdfplumberEngine().raw_tables(mini_pdf, [4, 3])
    assert [p.page for p in pages] == [4, 3]


@pytest.mark.parametrize("page", [0, 8])
def test_out_of_range_page_is_an_error(mini_pdf: Path, page: int) -> None:
    with pytest.raises(IndexError):
        PdfplumberEngine().raw_tables(mini_pdf, [page])
