"""One engine's cells, placed on the text layer's printed rows (EXTRACTION sections 3 and 4.1).

Per page and region:
1. Keep the engine strategy whose grid is row-accurate: most numeric cells that sit on exactly one
   printed row. Unilever's shaded current-year column makes "lines" grids pack seven figures into
   one cell; "text" grids do not. The choice is recorded.
2. Place every single-row cell on the text-layer row it overlaps most. Its characters are the
   printed words centred in it (ADR-001: engines say where, the text layer says what). Multi-row
   cells, cells with nothing printed under them, and cells whose edges cut through other words
   (prose fragments) never become figures.
3. Find the column-header band: the rows above the first figure that carry years, units or
   "Note(s)". Rows above that band (the subtitle) are not part of the table.
4. Cluster figure-like cells into columns by the x-overlap of their printed ink. A column is a
   value column when most of its cells parse as numbers. The column just left of the values is
   the note column when its header says "Note(s)", or 80 % of its cells look like note references
   (EXTRACTION section 3), or any cell is a letter-suffixed reference such as "15C", which can
   never be a value. A column headed by a year or a currency unit is never the note column. A
   note column is never a value column.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from finintel.locate.signals import SUPERSCRIPT_RATIO, PageView, normalise
from finintel.parse.engines.base import BBox, EngineTable, ParsedTables
from finintel.parse.text_layer import Word
from finintel.tables.numbers import ParsedNumber, parse_number
from finintel.tables.regions import Region

_YEAR = re.compile(r"^(?:19|20)\d{2}$")
NOTE_REF = _NOTE_REF = re.compile(
    r"^\d{1,2}(\.\d{1,2})?([,/]\s?\d{1,2}(\.\d{1,2})?)*$"
)  # EXTRACTION 3
LETTER_REF = _LETTER_REF = re.compile(r"^\d{1,2}[A-Z](?:\.\d{1,2})?$")  # "4B", "15C", "17A"
_UNPARSED = re.compile(r"^(?=\S*\d)\S{1,12}$|^(?:n/a|n/m|nm)$", re.IGNORECASE)
VALUE_SHARE = 0.5
NOTE_SLACK = 6.0  # pt either side of a printed Note(s) header
# pt a column-header row may start left of the first figure column. Note headers sit 36-80 pt
# left of the figures on the goldens and specs; subtitles start at the left margin, ~300 pt away.
HEADER_MARGIN = 120.0
CUT_TOLERANCE = 2.0  # pt a neighbouring word may reach into a cell before the cell 'cuts' it
NOTE_SHARE = 0.8
PREFERRED = ("lines", "text")  # on a tie, the ruled-table reading wins


@dataclass
class TextRow:
    """One printed row inside the region: its words and vertical band."""

    index: int
    words: list[tuple[Word, BBox]]
    top: float
    bottom: float

    @property
    def x0(self) -> float:
        return min(box[0] for _, box in self.words)


@dataclass(frozen=True)
class PlacedCell:
    text: str  # printed: the text-layer words centred in the engine's cell (ADR-001)
    engine_text: str  # what the engine itself returned for the cell
    parsed: ParsedNumber | None  # of the printed text
    bbox: BBox  # the engine's cell box
    ink: BBox  # the printed glyphs inside it; columns are measured on ink
    row: int
    cut: bool = False  # the engine's cell boundary cuts through other printed words


@dataclass
class Band:
    x0: float
    x1: float
    cells: list[PlacedCell] = field(default_factory=list)


@dataclass
class PageGrid:
    page: int
    strategy: str
    rows: list[TextRow]  # printed rows from the header band down
    header_rows: list[int]
    first_data_row: int | None
    value_bands: list[Band]
    note_band: Band | None
    note_evidence: str
    header_texts: dict[int, str]  # id(band) -> header text
    notes: list[str]
    header_top: float | None = None  # top of the column-header band
    #: x-range of the note column: the engine's note band, or, when the engine found none (sparse
    #: references are too few for a text-strategy grid), the printed "Note(s)" header.
    note_range: tuple[float, float] | None = None

    def header_words(self) -> list[tuple[int, Word, BBox]]:
        """(header row number, word, box) for every word in the column-header band."""
        order = {index: n for n, index in enumerate(self.header_rows)}
        return [
            (order[r.index], w, b)
            for r in self.rows
            if r.index in order
            for w, b in sorted(r.words, key=lambda wb: wb[1][0])
        ]

    def header_text(self, band: Band) -> str:
        return self.header_texts.get(id(band), "")


def text_rows(view: PageView, region: Region) -> list[TextRow]:
    x0, top, x1, bottom = region.bbox
    rows: list[TextRow] = []
    for row in view.row_boxes:
        inside = [
            (w, box)
            for w, box in row
            if box[1] >= top - 0.5
            and box[3] <= bottom + 0.5
            and x0 - 0.5 <= box[0]
            and box[2] <= x1 + 0.5
        ]
        if inside:
            body = [
                (w, b)
                for w, b in inside
                if w.size >= SUPERSCRIPT_RATIO * max(x.size for x, _ in inside)
            ]
            rows.append(
                TextRow(
                    index=len(rows),
                    words=inside,
                    top=min(b[1] for _, b in body),  # superscripts do not widen the band
                    bottom=max(b[3] for _, b in body),
                )
            )
    return rows


def build_grid(view: PageView, region: Region, parsed: ParsedTables) -> PageGrid:
    rows = text_rows(view, region)
    strategy, placed, notes = _choose(parsed, region, rows)
    data_cells = [
        c for c in placed if c.parsed is not None and not _YEAR.match(c.text) and not c.cut
    ]
    first_data = min((c.row for c in data_cells), default=None)
    data_left = min(
        (
            c.ink[0]
            for c in placed
            if first_data is not None
            and c.row >= first_data
            and not c.cut
            and (c.parsed is not None or _NOTE_REF.match(c.text) or _LETTER_REF.match(c.text))
        ),
        default=None,
    )
    header_rows = _header_rows(rows, first_data, data_left)
    start = header_rows[0] if header_rows else (first_data if first_data is not None else 0)
    kept_rows = [r for r in rows if r.index >= start]

    bands = _bands([c for c in placed if c.row >= start and _figure_like(c)])
    header_texts = {id(b): _header_text(rows, header_rows, b) for b in bands}
    body = [r.index for r in kept_rows if r.index not in header_rows]
    value_bands, note_band, evidence = _classify(bands, set(body), header_texts)
    if not value_bands:
        notes.append(f"p.{region.page}: no value column found")
    note_range = (note_band.x0, note_band.x1) if note_band is not None else None
    if note_band is None and value_bands:
        note_range = _note_header(rows, header_rows, value_bands[0].x0)
        if note_range is not None:
            evidence = 'header "Note(s)"; sparse references read from the print'
    unparsed = _attach_unparsed(placed, value_bands, set(body))
    if unparsed:
        notes.append(f"p.{region.page}: {unparsed} unparsed cells recorded (e.g. pence, n/a)")
    return PageGrid(
        page=region.page,
        strategy=strategy,
        rows=kept_rows,
        header_rows=header_rows,
        first_data_row=first_data,
        value_bands=value_bands,
        note_band=note_band,
        note_evidence=evidence,
        header_texts=header_texts,
        notes=notes,
        header_top=min((r.top for r in rows if r.index in header_rows), default=None),
        note_range=note_range,
    )


def _note_header(
    rows: Sequence[TextRow], header_rows: Sequence[int], values_x0: float
) -> tuple[float, float] | None:
    """The x-range of a printed "Note"/"Notes" header left of the value columns, if any."""
    for row in rows:
        if row.index not in header_rows:
            continue
        for word, box in row.words:
            if normalise(word.text) in ("note", "notes") and box[2] < values_x0:
                return (box[0] - NOTE_SLACK, box[2] + NOTE_SLACK)
    return None


def _choose(
    parsed: ParsedTables, region: Region, rows: Sequence[TextRow]
) -> tuple[str, list[PlacedCell], list[str]]:
    best: tuple[int, int, str, list[PlacedCell], tuple[int, int, int]] | None = None
    for rank, strategy in enumerate(PREFERRED):
        tables = [t for t in parsed.on_page(region.page, strategy) if _intersects(t, region)]
        placed, multi, unanchored, differs = _place(tables, region, rows)
        accurate = sum(1 for c in placed if c.parsed is not None)
        candidate = (accurate, -rank, strategy, placed, (multi, unanchored, differs))
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    assert best is not None
    accurate, _, strategy, placed, (multi, unanchored, differs) = best
    page = region.page
    notes = [
        f"p.{page}: {parsed.engine} strategy '{strategy}' ({accurate} single-row numeric cells)"
    ]
    if multi:
        notes.append(f"p.{page}: {multi} multi-row cells dropped (not split by guesswork)")
    if unanchored:
        notes.append(f"p.{page}: {unanchored} engine cells with no printed text under them dropped")
    if differs:
        notes.append(f"p.{page}: {differs} figures where the engine's text differs from the print")
    return strategy, placed, notes


def _place(
    tables: Sequence[EngineTable], region: Region, rows: Sequence[TextRow]
) -> tuple[list[PlacedCell], int, int, int]:
    """(cells, multi-row cells dropped, unanchored cells dropped, cells whose engine text
    differs from what is printed). Characters always come from the text layer."""
    placed: list[PlacedCell] = []
    multi = unanchored = 0
    x0, top, x1, bottom = region.bbox
    for table in tables:
        for cell in table.cells:
            if cell.bbox is None or not cell.text or not cell.text.strip():
                continue
            cx0, cy0, cx1, cy1 = cell.bbox
            if cy1 < top or cy0 > bottom or cx1 < x0 or cx0 > x1:
                continue
            overlapping = [
                r for r in rows if _overlap(cy0, cy1, r.top, r.bottom) > 0.5 * (r.bottom - r.top)
            ]
            tallest = max((r.bottom - r.top for r in overlapping), default=0.0)
            if "\n" in cell.text.strip() or (len(overlapping) > 1 and cy1 - cy0 > 1.5 * tallest):
                multi += 1  # the cell really spans rows
                continue
            if not overlapping:
                continue
            overlapping.sort(key=lambda r: -_overlap(cy0, cy1, r.top, r.bottom))
            row = overlapping[0]
            words = sorted(
                ((w, b) for w, b in row.words if cell.bbox[0] <= (b[0] + b[2]) / 2 <= cell.bbox[2]),
                key=lambda wb: wb[1][0],
            )
            if not words:
                unanchored += 1  # the engine reports text where nothing is printed
                continue
            printed = " ".join(w.text for w, _ in words)
            engine_text = " ".join(cell.text.split())
            # A cell whose edges cut through neighbouring printed words is a fragment of prose
            # (PyMuPDF reads "d 31 Dece" out of "for the year ended 31 December"): never a figure.
            cut = any(
                _overlap(b[0], b[2], cell.bbox[0], cell.bbox[2]) > CUT_TOLERANCE
                and not cell.bbox[0] <= (b[0] + b[2]) / 2 <= cell.bbox[2]
                for _, b in row.words
            )
            ink = (min(b[0] for _, b in words), row.top, max(b[2] for _, b in words), row.bottom)
            parsed = None if cut else parse_number(printed)
            placed.append(PlacedCell(printed, engine_text, parsed, cell.bbox, ink, row.index, cut))
    differs = sum(1 for c in placed if not c.cut and c.parsed and c.text != c.engine_text)
    return placed, multi, unanchored, differs


def _header_rows(
    rows: Sequence[TextRow], first_data: int | None, data_left: float | None
) -> list[int]:
    """The contiguous rows just above the first figure that sit over the figure columns: years,
    units, "Note(s)", and sub-headers such as "Restated" or "Underlying | Adjusting | Total".
    A row starting in the label area is a subtitle ("For the year ended 30 June 2025") or a section
    heading ("Assets"), never a column header."""
    if first_data is None:
        return []
    found: list[int] = []
    for row in reversed([r for r in rows if r.index < first_data]):
        over_figures = data_left is None or row.x0 >= data_left - HEADER_MARGIN
        if over_figures:
            found.append(row.index)
        elif found:
            break
    return sorted(found)


def _attach_unparsed(placed: Sequence[PlacedCell], bands: Sequence[Band], body: set[int]) -> int:
    """Record short figure-like cells the grammar refuses ("6.3p", "n/a") in the value column
    they sit in, unparsed. They never become numbers; they are not dropped either."""
    count = 0
    for cell in placed:
        if cell.row not in body or _figure_like(cell) or not _UNPARSED.match(cell.text):
            continue
        centre = (cell.ink[0] + cell.ink[2]) / 2
        for band in bands:
            if band.x0 - 2 <= centre <= band.x1 + 2:
                band.cells.append(cell)
                count += 1
                break
    return count


def _figure_like(cell: PlacedCell) -> bool:
    """Cells that can define a column: figures, nil dashes, note references, years, "Note(s)".
    Prose fragments (a footnote split by a text-strategy grid) span columns and would merge them."""
    if cell.cut:
        return False
    text = cell.text
    return (
        cell.parsed is not None
        or bool(_NOTE_REF.match(text) or _LETTER_REF.match(text) or _YEAR.match(text))
        or normalise(text) in ("note", "notes")
    )


def _ink(row: TextRow, bbox: BBox) -> BBox | None:
    """The text-layer glyphs whose centres fall inside an engine cell on this row."""
    boxes = [b for _, b in row.words if bbox[0] <= (b[0] + b[2]) / 2 <= bbox[2]]
    if not boxes:
        return None
    return (min(b[0] for b in boxes), row.top, max(b[2] for b in boxes), row.bottom)


def _bands(cells: Sequence[PlacedCell]) -> list[Band]:
    """Columns by printed extent. Engine boxes in text-strategy grids span the gaps between
    columns (a note column's box can reach under the first year's header); ink does not."""
    bands: list[Band] = []
    for cell in sorted(cells, key=lambda c: c.ink[0]):
        cx0, _, cx1, _ = cell.ink
        for band in bands:
            narrow = min(cx1 - cx0, band.x1 - band.x0) or 1.0
            if _overlap(cx0, cx1, band.x0, band.x1) >= 0.5 * narrow:
                band.cells.append(cell)
                band.x0, band.x1 = min(band.x0, cx0), max(band.x1, cx1)
                break
        else:
            bands.append(Band(cx0, cx1, [cell]))
    return sorted(bands, key=lambda b: b.x0)


def _classify(
    bands: Sequence[Band], body_rows: set[int], header_texts: dict[int, str]
) -> tuple[list[Band], Band | None, str]:
    numeric = []
    for band in bands:
        body = [c for c in band.cells if c.row in body_rows]
        if body and sum(1 for c in body if c.parsed is not None) >= VALUE_SHARE * len(body):
            numeric.append(band)
        elif body and any(_LETTER_REF.match(c.text) for c in body):
            numeric.append(band)  # a note column with letter references; judged below
    if not numeric:
        return [], None, ""
    leftmost = numeric[0]
    evidence = _note_evidence(leftmost, body_rows, header_texts.get(id(leftmost), ""))
    if evidence and len(numeric) > 1:
        return numeric[1:], leftmost, evidence
    values = [
        b
        for b in numeric
        if not any(_LETTER_REF.match(c.text) for c in b.cells if c.row in body_rows)
    ]
    return values, None, ""


def _note_evidence(band: Band, body_rows: set[int], header: str) -> str:
    tokens = normalise(header).split()
    if any(t in ("note", "notes") for t in tokens):
        return f'header "{header}"'
    if any(
        _YEAR.match(t) or any(sym in t for sym in "£$€") or t.startswith("million") for t in tokens
    ):
        return ""  # a period or unit header: this is a value column, whatever its cells look like
    body = [c.text for c in band.cells if c.row in body_rows]
    letters = [t for t in body if _LETTER_REF.match(t)]
    if letters:
        return f"letter-suffixed references {letters[:3]} cannot be values"
    refs = [t for t in body if _NOTE_REF.match(t)]
    if body and len(refs) >= NOTE_SHARE * len(body):
        return f"{len(refs)}/{len(body)} cells are note references"
    return ""


def _header_text(rows: Sequence[TextRow], header_rows: Sequence[int], band: Band) -> str:
    words = [
        w.text
        for r in rows
        if r.index in header_rows
        for w, box in sorted(r.words, key=lambda wb: wb[1][0])
        if _overlap(box[0], box[2], band.x0 - 3, band.x1 + 3) > 0
    ]
    return " ".join(words)


def _intersects(table: EngineTable, region: Region) -> bool:
    tx0, ty0, tx1, ty1 = table.bbox
    x0, top, x1, bottom = region.bbox
    return _overlap(tx0, tx1, x0, x1) > 0 and _overlap(ty0, ty1, top, bottom) > 0


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))
