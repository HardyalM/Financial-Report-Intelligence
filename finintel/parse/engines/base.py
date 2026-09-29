"""Engine interface shared by every table engine (EXTRACTION sections 4.1 and 5.1a).

Every engine returns the same `ParsedTables`: grids of cells with their printed text and boxes,
exactly as the engine produced them. Engines propose cells; the text layer later decides row,
column and period (ADR-001), so nothing here interprets a number.

Coordinates are PDF points on the unrotated page, origin top-left, like the text layer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

BBox = tuple[float, float, float, float]


class EngineFamily(StrEnum):
    """Agreement counts only across families (EXTRACTION section 5.1a)."""

    IMAGE_LAYOUT = "image_layout"
    TEXT_LAYER = "text_layer"
    VISION = "vision"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EngineCell(_Frozen):
    row: int
    col: int
    text: str | None  # as the engine returned it; None when the engine reports no cell
    bbox: BBox | None


class EngineTable(_Frozen):
    page: int  # 1-based PDF page index
    strategy: str  # e.g. "text" or "lines"
    clip: BBox | None  # the region the engine was asked to read, if any
    bbox: BBox
    n_rows: int
    n_cols: int
    cells: tuple[EngineCell, ...]


class ParsedTables(_Frozen):
    engine: str
    engine_version: str
    family: EngineFamily
    tables: tuple[EngineTable, ...] = ()
    errors: tuple[str, ...] = ()  # "p.142: page_unreadable: KeyError"

    def on_page(self, page: int, strategy: str | None = None) -> tuple[EngineTable, ...]:
        return tuple(
            t
            for t in self.tables
            if t.page == page and (strategy is None or t.strategy == strategy)
        )


class TableEngine(Protocol):
    """A table engine. Engines propose cells; the text layer decides row, column and period."""

    name: str
    family: EngineFamily

    def parse(
        self,
        pdf_path: Path,
        pages: Sequence[int] | None = None,
        clips: Mapping[int, Sequence[BBox]] | None = None,
    ) -> ParsedTables:
        """Parse the given 1-based PDF pages (all pages if None), optionally within clip boxes."""
        ...
