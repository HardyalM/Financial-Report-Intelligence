"""PymupdfTablesEngine: PyMuPDF `find_tables()` (text_layer family).

A different table algorithm over the same embedded text as pdfplumber, so the two are correlated
and count as one family for agreement (EXTRACTION section 5.1a). Both strategies run on every
requested region: "lines" suits ruled tables; "text" suits whitespace-aligned UK statements. The
table builder (finintel.tables) keeps whichever grid is row-accurate and records the choice.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pymupdf

from finintel.parse.engines.base import (
    BBox,
    EngineCell,
    EngineFamily,
    EngineTable,
    ParsedTables,
)

#: Bump when the output shape or the strategies change. Part of the cache key.
PARSE_VERSION = "1"
STRATEGIES = ("lines", "text")

# PyMuPDF prints an install advice to stdout on the first find_tables() call; it would corrupt
# `--json` output. This is its documented switch.
pymupdf.no_recommend_layout()


def _bbox(values: Sequence[float]) -> BBox:
    x0, y0, x1, y1 = (round(float(v), 2) for v in values)
    return (x0, y0, x1, y1)


class PymupdfTablesEngine:
    name = "pymupdf_tables"
    family = EngineFamily.TEXT_LAYER
    version = f"pymupdf {pymupdf.VersionBind}"

    def parse(
        self,
        pdf_path: Path,
        pages: Sequence[int] | None = None,
        clips: Mapping[int, Sequence[BBox]] | None = None,
    ) -> ParsedTables:
        tables: list[EngineTable] = []
        errors: list[str] = []
        with pymupdf.open(pdf_path) as doc:
            numbers = list(pages) if pages is not None else list(range(1, doc.page_count + 1))
            for number in numbers:
                if not 1 <= number <= doc.page_count:
                    raise IndexError(f"page {number} outside 1..{doc.page_count}")
                page = doc[number - 1]
                regions: Sequence[BBox | None] = (clips or {}).get(number) or [None]
                for clip in regions:
                    for strategy in STRATEGIES:
                        try:
                            found = page.find_tables(
                                clip=pymupdf.Rect(clip) if clip else None, strategy=strategy
                            )
                        except Exception as exc:  # MuPDF raises several types on damaged pages
                            errors.append(f"p.{number}: page_unreadable: {type(exc).__name__}")
                            continue
                        tables.extend(_table(number, strategy, clip, t) for t in found.tables)
        return ParsedTables(
            engine=self.name,
            engine_version=self.version,
            family=self.family,
            tables=tuple(tables),
            errors=tuple(errors),
        )


def _table(page: int, strategy: str, clip: BBox | None, table: Any) -> EngineTable:
    texts = table.extract()
    cells = [
        EngineCell(
            row=r,
            col=c,
            text=texts[r][c] if r < len(texts) and c < len(texts[r]) else None,
            bbox=_bbox(box) if box is not None else None,
        )
        for r, row in enumerate(table.rows)
        for c, box in enumerate(row.cells)
    ]
    return EngineTable(
        page=page,
        strategy=strategy,
        clip=clip,
        bbox=_bbox(table.bbox),
        n_rows=int(table.row_count),
        n_cols=int(table.col_count),
        cells=tuple(cells),
    )
