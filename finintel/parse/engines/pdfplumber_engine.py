"""PdfplumberEngine: the `pdfplumber` table engine (text_layer family).

Two outputs, both exactly as pdfplumber returns them:
- `raw_tables` (M1): inspection dumps, per page, both strategies.
- `parse` (M2.2): `ParsedTables` for the table builder, optionally clipped to statement regions.

pdfplumber coordinates are PDF points, origin top-left. When the CropBox does not start at the
MediaBox origin, cell boxes are shifted into the text layer's (CropBox) space.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pdfplumber
from pydantic import BaseModel, ConfigDict

from finintel.parse.engines.base import EngineCell, EngineFamily, EngineTable, ParsedTables

#: Bump when the dump format or the strategies change. Part of the raw-table cache key.
RAW_TABLES_VERSION = "1"
#: Bump when `parse` output changes. Part of the parsed-tables cache key.
PARSE_VERSION = "1"

#: "lines" finds ruled tables; "text" finds whitespace-aligned ones, typical of UK statements.
STRATEGIES: dict[str, dict[str, Any]] = {
    "lines": {},
    "text": {"vertical_strategy": "text", "horizontal_strategy": "text"},
}

BBox = tuple[float, float, float, float]


def _bbox(values: Sequence[float], dx: float = 0.0, dy: float = 0.0) -> BBox:
    x0, y0, x1, y1 = values
    return (round(x0 - dx, 2), round(y0 - dy, 2), round(x1 - dx, 2), round(y1 - dy, 2))


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

    def parse(
        self,
        pdf_path: Path,
        pages: Sequence[int] | None = None,
        clips: Mapping[int, Sequence[BBox]] | None = None,
    ) -> ParsedTables:
        tables: list[EngineTable] = []
        errors: list[str] = []
        with pdfplumber.open(pdf_path) as pdf:
            total = len(pdf.pages)
            numbers = list(pages) if pages is not None else list(range(1, total + 1))
            for number in numbers:
                if not 1 <= number <= total:
                    raise IndexError(f"page {number} outside 1..{total}")
                page = pdf.pages[number - 1]
                dx, dy = float(page.cropbox[0]), float(page.cropbox[1])
                regions: Sequence[BBox | None] = (clips or {}).get(number) or [None]
                for clip in regions:
                    try:
                        area = page.crop(_within(page, clip, dx, dy)) if clip else page
                        for strategy, settings in STRATEGIES.items():
                            tables.extend(
                                _engine_table(number, strategy, clip, t, dx, dy)
                                for t in area.find_tables(settings)
                            )
                    except Exception as exc:  # pdfminer raises a zoo of types on damaged pages
                        errors.append(f"p.{number}: page_unreadable: {type(exc).__name__}")
        return ParsedTables(
            engine=self.name,
            engine_version=self.version,
            family=self.family,
            tables=tuple(tables),
            errors=tuple(errors),
        )


def _within(page: Any, clip: BBox, dx: float, dy: float) -> BBox:
    """A text-layer clip box in pdfplumber page space, clamped to the page."""
    px0, ptop, px1, pbottom = page.bbox
    x0, y0, x1, y1 = clip
    return (max(px0, x0 + dx), max(ptop, y0 + dy), min(px1, x1 + dx), min(pbottom, y1 + dy))


def _engine_table(
    page: int, strategy: str, clip: BBox | None, table: Any, dx: float, dy: float
) -> EngineTable:
    texts = table.extract()
    cells = [
        EngineCell(
            row=r,
            col=c,
            text=texts[r][c] if r < len(texts) and c < len(texts[r]) else None,
            bbox=_bbox(box, dx, dy) if box is not None else None,
        )
        for r, row in enumerate(table.rows)
        for c, box in enumerate(row.cells)
    ]
    n_cols = max((len(row.cells) for row in table.rows), default=0)
    return EngineTable(
        page=page,
        strategy=strategy,
        clip=clip,
        bbox=_bbox(table.bbox, dx, dy),
        n_rows=len(table.rows),
        n_cols=n_cols,
        cells=tuple(cells),
    )


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
