"""StatementTable (EXTRACTION section 4.1): one engine's reading of one statement.

The engine decides where cells are; the text layer decides what is printed in them (ADR-001).
Rows, labels, styles and sections come from the text layer; each value cell holds the printed
words centred in the engine's cell, next to the engine's own reading of it. Periods,
restatement and the statutory column (`period_id`, `is_restated`, `is_total_column`) are decided
in M2.3 and are unset here.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from finintel.locate.models import Scope, StatementType
from finintel.parse.engines.base import BBox, EngineFamily


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ColumnKind(StrEnum):
    NOTE = "note"
    VALUE = "value"


class RowStyle(StrEnum):
    HEADER = "header"  # a section heading: label, no figures ("Current assets")
    NORMAL = "normal"
    SUBTOTAL = "subtotal"
    TOTAL = "total"


class Column(_Frozen):
    column_id: str  # "note", "v1", "v2", ... left to right
    kind: ColumnKind
    header_text: str  # the column's header band as printed, e.g. "€ million 2024"
    x0: float
    x1: float
    evidence: str  # why this is a note or value column
    period_id: str | None = None  # M2.3
    is_restated: bool = False  # M2.3
    is_total_column: bool = False  # M2.3


class Cell(_Frozen):
    raw_text: str  # printed characters: text-layer words centred in the engine's cell
    engine_text: str  # the engine's own reading of the cell (kept for review and voting)
    parsed_value: Decimal | None  # of raw_text; None when the grammar does not accept it
    bbox: BBox  # the engine's own cell box: its claim, which anchoring (M2.5) tests
    ink: BBox  # the printed glyphs in that box, from the text layer: what a reviewer sees
    page: int


class Row(_Frozen):
    row_id: str  # "141:12": PDF page and row index on that page
    label_text: str  # from the text layer; wrapped lines joined
    note_ref: str | None
    section_header: str | None
    sections: tuple[str, ...]  # enclosing section headings, outermost first
    indent_level: int
    style: RowStyle
    page: int
    bbox: BBox
    cells: dict[str, Cell]  # column_id -> cell (value columns only)


class StatementTable(_Frozen):
    statement_type: StatementType
    scope: Scope | None
    engine: str
    engine_version: str
    family: EngineFamily
    pages: tuple[int, ...]
    strategies: dict[int, str]  # page -> the engine strategy whose grid was used
    columns: tuple[Column, ...]
    rows: tuple[Row, ...]
    notes: tuple[str, ...] = ()  # what the builder saw and did: merges, dropped cells, choices

    @property
    def value_columns(self) -> tuple[Column, ...]:
        return tuple(c for c in self.columns if c.kind is ColumnKind.VALUE)

    def cells(self) -> list[tuple[Row, Column, Cell]]:
        by_id = {c.column_id: c for c in self.columns}
        return [(row, by_id[cid], cell) for row in self.rows for cid, cell in row.cells.items()]
