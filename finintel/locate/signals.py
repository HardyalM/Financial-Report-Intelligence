"""Page primitives shared by the locator and the inspector: printed tokens and page geometry.

Everything here reads the text layer in *display* coordinates (`PageText.visual_bbox`), so "the
top of the page" means what a reader sees, including on rotated pages. Nothing here decides
anything; the locator scores with these facts and the inspector reports them.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import cached_property
from statistics import median

from finintel.parse.text_layer import BBox, Line, PageText, TextLayer, Word

NUMERIC = re.compile(
    r"^[(\-\u2013\u2212]?[£$€]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\)?[*\u2020\u2021]?$"
    r"|^[\-\u2013\u2014]$"  # a lone dash prints nil
)
YEAR = re.compile(r"^(?:19|20)\d{2}$")
UNIT = re.compile(
    r"(?:us\$|£|\$|€)\s?(?:millions?|mn|m|['\u2019]000|000|k)(?![a-z0-9])|\beurm\b", re.IGNORECASE
)
_LETTER = re.compile(r"[A-Za-z]")

TITLE_REGION = 0.25  # top quarter of the displayed page
TITLE_SIZE_RATIO = 1.2  # x the page's median word size
HEADER_REGION = 0.5  # column headers sit in the top half
CHROME_PAGE_SHARE = 0.25  # a line on at least this share of pages is navigation, not content
CHROME_MIN_PAGES = 3
SUPERSCRIPT_RATIO = 0.75  # glyphs smaller than this x the median size are superscripts


def normalise(text: str) -> str:
    """Lower-case, NFKC, straight quotes, collapsed whitespace. For matching, never for storage."""
    text = unicodedata.normalize("NFKC", text).replace("\u2019", "'").replace("\u2018", "'")
    return " ".join(text.lower().split())


def collapse(text: str) -> str:
    return " ".join(text.split())


@dataclass(frozen=True)
class VisualLine:
    line: Line
    bbox: BBox  # display coordinates
    text: str  # whitespace collapsed, case kept
    norm: str  # normalised, for matching


class PageView:
    """Display-space facts about one page, computed once."""

    def __init__(self, page: PageText, chrome: frozenset[str] = frozenset()) -> None:
        self.page = page
        self.chrome = chrome
        self.width, self.height = page.visual_size

    @cached_property
    def words(self) -> tuple[tuple[Word, BBox], ...]:
        return tuple((w, self.page.visual_bbox(w.bbox)) for w in self.page.words)

    @cached_property
    def lines(self) -> tuple[VisualLine, ...]:
        out = [
            VisualLine(
                line, self.page.visual_bbox(line.bbox), collapse(line.text), normalise(line.text)
            )
            for line in self.page.lines
        ]
        return tuple(sorted(out, key=lambda v: (v.bbox[1], v.bbox[0])))

    @cached_property
    def median_size(self) -> float | None:
        return median(w.size for w in self.page.words) if self.page.words else None

    @cached_property
    def rows(self) -> tuple[tuple[Word, ...], ...]:
        """Printed rows, left to right. Table cells often sit in separate PyMuPDF blocks, so
        (block, line) ids alone do not give table rows; vertical centres do."""
        return tuple(tuple(w for w, _ in row) for row in _rows(self.words))

    @cached_property
    def row_boxes(self) -> tuple[tuple[tuple[Word, BBox], ...], ...]:
        return tuple(tuple(row) for row in _rows(self.words))

    # --------------------------------------------------------------- regions

    def is_chrome(self, line: VisualLine) -> bool:
        return line.norm in self.chrome

    @cached_property
    def title_lines(self) -> tuple[VisualLine, ...]:
        """Title-like lines: top quarter, larger than the median word or bold, not chrome."""
        if self.median_size is None:
            return ()
        limit = self.height * TITLE_REGION
        return tuple(
            v
            for v in self.lines
            if v.bbox[1] < limit
            and _LETTER.search(v.text)
            and not self.is_chrome(v)
            and (v.line.size >= TITLE_SIZE_RATIO * self.median_size or v.line.bold)
        )

    def band(self, fraction: float, *, bottom: bool = False) -> tuple[VisualLine, ...]:
        """Non-chrome lines in the top (or bottom) `fraction` of the displayed page."""
        if bottom:
            limit = self.height * (1 - fraction)
            return tuple(v for v in self.lines if v.bbox[1] >= limit and not self.is_chrome(v))
        limit = self.height * fraction
        return tuple(v for v in self.lines if v.bbox[1] < limit and not self.is_chrome(v))

    # --------------------------------------------------------------- numbers

    @cached_property
    def numeric_share(self) -> float:
        words = self.page.words
        return (
            round(sum(1 for w in words if NUMERIC.match(w.text)) / len(words), 4) if words else 0.0
        )

    @cached_property
    def numeric_rows(self) -> int:
        return sum(1 for row in self.rows if sum(bool(NUMERIC.match(w.text)) for w in row) >= 2)

    @cached_property
    def header_years(self) -> tuple[str, ...]:
        """Years from rows with two or more year tokens in the top half (column headers)."""
        years: set[str] = set()
        for row in self.row_boxes:
            if row and row[0][1][1] < self.height * HEADER_REGION:
                found = [w.text for w, _ in row if YEAR.match(w.text)]
                if len(found) >= 2:
                    years.update(found)
        return tuple(sorted(years, reverse=True))

    @cached_property
    def unit_tokens(self) -> tuple[str, ...]:
        return tuple(sorted({normalise(m.group(0)) for m in UNIT.finditer(self.page.text)}))

    @cached_property
    def header_unit_tokens(self) -> tuple[str, ...]:
        text = "\n".join(v.text for v in self.lines if v.bbox[1] < self.height * HEADER_REGION)
        return tuple(sorted({normalise(m.group(0)) for m in UNIT.finditer(text)}))

    @cached_property
    def value_columns(self) -> int:
        """Number of right-aligned numeric columns in the page's table rows."""
        edges = sorted(
            box[2]
            for row in self.row_boxes
            if sum(bool(NUMERIC.match(w.text)) for w, _ in row) >= 2
            for w, box in row
            if NUMERIC.match(w.text)
        )
        clusters: list[list[float]] = []
        for edge in edges:
            if clusters and edge - clusters[-1][-1] <= 6.0:
                clusters[-1].append(edge)
            else:
                clusters.append([edge])
        support = max(3, round(0.2 * self.numeric_rows))
        return sum(1 for c in clusters if len(c) >= support)


def _rows(words: Sequence[tuple[Word, BBox]]) -> Iterable[list[tuple[Word, BBox]]]:
    """Group words into printed rows by vertical centre. Superscripts and other undersized glyphs
    (footnote markers such as "(a)") sit higher than their line; they join the row they overlap
    instead of starting a row of their own."""
    if not words:
        return
    sizes = sorted(w.size for w, _ in words)
    median_size = sizes[len(sizes) // 2]
    tolerance = max(2.0, 0.35 * median_size)
    small = [wb for wb in words if wb[0].size < SUPERSCRIPT_RATIO * median_size]
    ordered = sorted(
        (wb for wb in words if wb[0].size >= SUPERSCRIPT_RATIO * median_size),
        key=lambda wb: ((wb[1][1] + wb[1][3]) / 2, wb[1][0]),
    )
    rows: list[list[tuple[Word, BBox]]] = []
    centre = 0.0
    for item in ordered:
        mid = (item[1][1] + item[1][3]) / 2
        if not rows or mid - centre > tolerance:
            rows.append([])
            centre = mid
        rows[-1].append(item)
    for item in small:
        top, bottom = item[1][1], item[1][3]
        best = max(
            rows,
            key=lambda r: min(bottom, max(b[3] for _, b in r)) - max(top, min(b[1] for _, b in r)),
            default=None,
        )
        if best is not None and min(bottom, max(b[3] for _, b in best)) > max(
            top, min(b[1] for _, b in best)
        ):
            best.append(item)
        else:
            rows.append([item])
    rows.sort(key=lambda r: min((b[1] + b[3]) / 2 for _, b in r))
    for row in rows:
        yield sorted(row, key=lambda wb: wb[1][0])


def detect_chrome(layer: TextLayer) -> frozenset[str]:
    """Normalised header-band lines repeated on at least a quarter of the pages: navigation bars,
    report titles, section tabs. They say nothing about the page they sit on."""
    seen: Counter[str] = Counter()
    for page in layer.pages:
        view = PageView(page)
        seen.update({v.norm for v in view.band(TITLE_REGION) if _LETTER.search(v.norm)})
    threshold = max(CHROME_MIN_PAGES, CHROME_PAGE_SHARE * layer.page_count)
    return frozenset(text for text, count in seen.items() if count >= threshold)
