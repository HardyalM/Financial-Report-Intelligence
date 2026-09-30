"""Statement rows from the text layer (EXTRACTION section 4.1).

The label is the text-layer words left of the note and value columns on the same printed row,
never the engine's label cell (text-strategy grids split labels mid-word). Style comes from the
text layer too: bold figures, ruling lines within 3 pt of the figures, "Total" labels, and
unlabelled rows with figures (subtotals).

Wrapped labels are joined when the continuation line starts in lower case. A heading ending in a
colon ("Pensions and post-retirement healthcare liabilities:") opens a sub-list for the more
indented rows below it; it never replaces the main section heading, which arithmetic checks use.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

from finintel.locate.signals import SUPERSCRIPT_RATIO, PageView, normalise
from finintel.parse.engines.base import BBox
from finintel.tables.grid import LETTER_REF, NOTE_REF, PageGrid
from finintel.tables.models import Cell, Row, RowStyle

RULE_DISTANCE = 3.0  # pt between a ruling line and the figures it marks (EXTRACTION 4.1)
INDENT_STEP = 5.0  # pt per indent level
WRAP_GAP = 1.2  # x the line height: a continuation line sits directly below
_DIGIT = re.compile(r"\d")
GRID_RULE_SHARE = 0.5  # when this share of rows is ruled, rules are a grid, not emphasis


@dataclass
class DraftRow:
    page: int
    top: float
    bottom: float
    label: str
    label_x0: float | None
    label_bold: bool
    cells: dict[str, Cell] = field(default_factory=dict)
    note_ref: str | None = None
    values_bold: bool = False
    rule_above: bool = False
    rule_below: bool = False
    x0: float = 0.0
    x1: float = 0.0


def page_drafts(view: PageView, grid: PageGrid, column_of: Mapping[int, str]) -> list[DraftRow]:
    if not grid.value_bands:
        return []
    lefts = [b.x0 for b in grid.value_bands] + ([grid.note_range[0]] if grid.note_range else [])
    label_right = min(lefts) - 2.0
    value_x0 = min(b.x0 for b in grid.value_bands)
    value_x1 = max(b.x1 for b in grid.value_bands)
    header = set(grid.header_rows)
    drafts: list[DraftRow] = []
    for row in grid.rows:
        if row.index in header:
            continue
        label_words = [(w, box) for w, box in row.words if box[2] <= label_right + 1.0]
        full_size = [
            (w, box)
            for w, box in label_words
            if w.size >= SUPERSCRIPT_RATIO * max(x.size for x, _ in row.words)
        ]
        draft = DraftRow(
            page=grid.page,
            top=row.top,
            bottom=row.bottom,
            label=" ".join(w.text for w, _ in label_words),
            label_x0=min((box[0] for _, box in full_size), default=None),
            label_bold=bool(full_size) and all(w.bold for w, _ in full_size),
            x0=min(box[0] for _, box in row.words),
            x1=max(box[2] for _, box in row.words),
        )
        bold_cells: list[bool] = []
        for band in grid.value_bands:
            placed = [c for c in band.cells if c.row == row.index]
            if placed:
                cell = placed[0]
                draft.cells[column_of[id(band)]] = Cell(
                    raw_text=cell.text,
                    engine_text=cell.engine_text,
                    parsed_value=cell.parsed.value if cell.parsed else None,
                    bbox=cell.bbox,
                    ink=cell.ink,
                    page=grid.page,
                )
                in_cell = [
                    w
                    for w, box in row.words
                    if box[0] >= cell.ink[0] - 1 and box[2] <= cell.ink[2] + 1
                ]
                bold_cells.append(bool(in_cell) and all(w.bold for w in in_cell))
        # Emphasis is every figure in bold; one bold column (the current year) is house style.
        draft.values_bold = bool(bold_cells) and all(bold_cells)
        if grid.note_band is not None:
            notes = [c.text for c in grid.note_band.cells if c.row == row.index]
            draft.note_ref = notes[0] if notes else None
        elif grid.note_range is not None:
            lo, hi = grid.note_range
            refs = [
                w.text
                for w, box in row.words
                if lo <= (box[0] + box[2]) / 2 <= hi
                and (NOTE_REF.match(w.text) or LETTER_REF.match(w.text))
            ]
            draft.note_ref = " ".join(refs) or None
        if draft.cells:
            draft.rule_above, draft.rule_below = _rules(view, draft, value_x0, value_x1)
        drafts.append(draft)
    drafts = _drop_trailing(drafts)
    figures = [d for d in drafts if d.cells]
    if figures:
        figures[0].rule_above = False  # the column-header underline, not emphasis
    if figures and sum(d.rule_above for d in figures) >= GRID_RULE_SHARE * len(figures):
        for d in figures:  # every row is ruled: rules are a grid, not emphasis
            d.rule_above = d.rule_below = False
    return drafts


def join_wrapped(drafts: Sequence[DraftRow]) -> list[DraftRow]:
    out: list[DraftRow] = []
    for draft in drafts:
        prev = out[-1] if out else None
        if prev is not None and _continues(prev, draft):
            if not prev.cells and not prev.note_ref:  # label wrapped; figures on the last line
                out[-1] = replace(
                    draft, label=f"{prev.label} {draft.label}", label_x0=prev.label_x0, top=prev.top
                )
                continue
            if not draft.cells and not draft.note_ref:  # figures on the first line
                out[-1] = replace(prev, label=f"{prev.label} {draft.label}", bottom=draft.bottom)
                continue
        out.append(draft)
    return out


def finalise(drafts: Sequence[DraftRow]) -> list[Row]:
    left = min((d.label_x0 for d in drafts if d.label_x0 is not None), default=0.0)
    main: str | None = None
    sub: tuple[str, int] | None = None
    counters: dict[int, int] = {}
    rows: list[Row] = []
    for draft in drafts:
        indent = round(((draft.label_x0 or left) - left) / INDENT_STEP)
        index = counters[draft.page] = counters.get(draft.page, 0) + 1
        if not draft.cells:
            sections: tuple[str, ...] = tuple(s for s in (main,) if s)
            section_header = main
            if draft.label.rstrip().endswith(":"):
                sub = (draft.label, indent)
            else:
                main, sub = draft.label, None
            style = RowStyle.HEADER
        else:
            if sub is not None and indent <= sub[1]:
                sub = None
            sections = tuple(s for s in (main, sub[0] if sub else None) if s)
            section_header = main
            style = _style(draft)
        rows.append(
            Row(
                row_id=f"{draft.page}:{index}",
                label_text=draft.label,
                note_ref=draft.note_ref,
                section_header=section_header,
                sections=sections,
                indent_level=max(indent, 0),
                style=style,
                page=draft.page,
                bbox=_bbox(draft),
                cells=draft.cells,
            )
        )
    return rows


def _style(draft: DraftRow) -> RowStyle:
    label = normalise(draft.label)
    if draft.values_bold or label.startswith("total") or (draft.rule_above and draft.rule_below):
        return RowStyle.TOTAL
    if not label or draft.rule_above:
        return RowStyle.SUBTOTAL
    return RowStyle.NORMAL


def _rules(view: PageView, draft: DraftRow, x0: float, x1: float) -> tuple[bool, bool]:
    above = below = False
    for rule in view.page.rules:
        if min(rule.x1, x1) - max(rule.x0, x0) <= 0:
            continue
        if draft.top - RULE_DISTANCE - 1.0 <= rule.y <= draft.top + 1.0:
            above = True
        if draft.bottom - 1.0 <= rule.y <= draft.bottom + RULE_DISTANCE + 1.0:
            below = True
    return above, below


def _continues(prev: DraftRow, draft: DraftRow) -> bool:
    if prev.page != draft.page or not prev.label or not draft.label:
        return False
    if prev.label.rstrip().endswith(":") or not draft.label[0].islower():
        return False
    height = max(prev.bottom - prev.top, 1.0)
    return draft.top - prev.bottom <= WRAP_GAP * height


def _drop_trailing(drafts: list[DraftRow]) -> list[DraftRow]:
    """Footnote prose after the last row with a figure is not part of the table. A figure is any
    cell with a digit: "6.3p" stays (recorded, unparsed); "in equity, consolida" goes."""
    last = max(
        (
            i
            for i, d in enumerate(drafts)
            if any(_DIGIT.search(c.raw_text) for c in d.cells.values())
        ),
        default=-1,
    )
    return drafts[: last + 1]


def _bbox(draft: DraftRow) -> BBox:
    xs = [draft.x0, *(c.ink[0] for c in draft.cells.values())]
    xe = [draft.x1, *(c.ink[2] for c in draft.cells.values())]
    return (round(min(xs), 2), round(draft.top, 2), round(max(xe), 2), round(draft.bottom, 2))
