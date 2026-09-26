"""PdfplumberEngine: the `pdfplumber` table engine (text_layer family).

M1 provides raw table dumps for inspection: every table pdfplumber finds, under two strategies,
with cell text and cell boxes exactly as returned. Normalisation into `StatementTable` (rows
aligned to text-layer lines, note column, number grammar) is M2.2.

pdfplumber coordinates are PDF points, origin top-left, relative to the page's MediaBox. Each dump
records the page bbox so M2.2 can reconcile any MediaBox/CropBox offset with the text layer.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pdfplumber
from pydantic import BaseModel, ConfigDict

from finintel._placeholders import not_yet
from finintel.parse.engines.base import EngineFamily, ParsedTables

#: Bump when the dump format or the strategies change. Part of the raw-table cache key.
RAW_TABLES_VERSION = "1"

#: "lines" finds ruled tables; "text" finds whitespace-aligned ones, typical of UK statements.
STRATEGIES: dict[str, dict[str, Any]] = {
    "lines": {},
    "text": {"vertical_strategy": "text", "horizontal_strategy": "text"},
}

BBox = tuple[float, float, float, float]


def _bbox(values: Sequence[float]) -> BBox:
    x0, y0, x1, y1 = (round(float(v), 2) for v in values)
    return (x0, y0, x1, y1)


class RawTable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy: str
    bbox: BBox
    rows: tuple[tuple[str | None, ...], ...]
    cell_bboxes: tuple[tuple[BBox | None, ...], ...]


class RawPageTables(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    page: int  # 1-based PDF page index
    page_bbox: BBox
    tables: tuple[RawTable, ...] = ()
    error: str | None = None

    def count(self, strategy: str) -> int:
        return sum(1 for t in self.tables if t.strategy == strategy)


class PdfplumberEngine:
    name = "pdfplumber"
    family = EngineFamily.TEXT_LAYER
    version = str(pdfplumber.__version__)

    def raw_tables(self, pdf_path: Path, pages: Sequence[int]) -> list[RawPageTables]:
        """Raw tables for the given 1-based pages, in the order requested."""
        out = []
        with pdfplumber.open(pdf_path) as pdf:
            total = len(pdf.pages)
            for number in pages:
                if not 1 <= number <= total:
                    raise IndexError(f"page {number} outside 1..{total}")
                out.append(_page_tables(pdf.pages[number - 1], number))
        return out

    def parse(self, pdf_path: Path, pages: list[int] | None = None) -> ParsedTables:
        not_yet("M2.2", "PdfplumberEngine.parse (StatementTable normalisation)")


def _page_tables(page: Any, number: int) -> RawPageTables:
    try:
        tables = [
            _raw_table(strategy, table)
            for strategy, settings in STRATEGIES.items()
            for table in page.find_tables(settings)
        ]
    except Exception as exc:  # pdfminer raises a zoo of types on damaged pages
        return RawPageTables(
            page=number, page_bbox=_bbox(page.bbox), error=f"page_unreadable: {type(exc).__name__}"
        )
    return RawPageTables(page=number, page_bbox=_bbox(page.bbox), tables=tuple(tables))


def _raw_table(strategy: str, table: Any) -> RawTable:
    rows = tuple(tuple(cell for cell in row) for row in table.extract())
    boxes = tuple(
        tuple(_bbox(cell) if cell is not None else None for cell in row.cells) for row in table.rows
    )
    return RawTable(strategy=strategy, bbox=_bbox(table.bbox), rows=rows, cell_bboxes=boxes)
