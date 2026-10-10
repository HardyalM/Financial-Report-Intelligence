"""Where a located statement sits on each of its pages (EXTRACTION section 2).

A statement region runs from below its title down to the next statement heading on the page, or
to the page foot. Headings are found anywhere on the page, not only in the title region: Unilever
prints its statement of comprehensive income under the income statement on the same page, and
"Net profit" appears in both. On a two-page spread the region is the half holding the statement.

A statement printed in two side-by-side panels on one landscape page (Tesco: assets on the left,
liabilities and equity on the right, company_c p.139) is two regions on that page, left then right,
read one after the other like a continuation, never across the middle (`_panels`).

Regions are in unrotated page space. Rotated statement pages are not supported in v1: the
builder records that plainly instead of guessing.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from finintel.locate.models import StatementLocation, StatementType
from finintel.locate.signals import TITLE_SIZE_RATIO, PageView, VisualLine
from finintel.locate.titles import match_title
from finintel.parse.engines.base import BBox
from finintel.parse.text_layer import TextLayer

FOOTER_MARGIN = 0.06  # folios and running footers are not table rows
LANDSCAPE = 1.2  # width / height above which a page may carry two panels
_NUMBER = re.compile(r"^\(?[\d,.]+\)?$")
_LABEL = re.compile(r"^[A-Za-z]")


@dataclass(frozen=True)
class Region:
    page: int
    bbox: BBox  # x0, top, x1, bottom
    title_bottom: float | None  # None on a continuation page without a title
    half: str | None  # "left" or "right" on a spread
    title_top: float | None = None


def statement_regions(layer: TextLayer, location: StatementLocation) -> list[Region]:
    regions: list[Region] = []
    half: str | None = None
    for number in location.pages:
        page = layer.page(number)
        view = PageView(page)
        headings = _headings(view)
        own = [
            (line, kind)
            for line, kind, continued in headings
            if kind is location.statement_type and not continued
        ]
        title = own[0][0] if own else None
        x0, x1 = 0.0, page.width
        if location.spread:
            if title is not None:
                half = "left" if (title.bbox[0] + title.bbox[2]) / 2 < page.width / 2 else "right"
            half = half or "left"
            x0, x1 = (0.0, page.width / 2) if half == "left" else (page.width / 2, page.width)
        top = title.bbox[3] if title is not None else 0.0
        below = [
            line.bbox[1]
            for line, kind, continued in headings
            if line.bbox[1] > top + 1
            and x0 <= (line.bbox[0] + line.bbox[2]) / 2 <= x1
            and not (kind is location.statement_type and continued)
        ]
        bottom = min(below, default=page.height * (1 - FOOTER_MARGIN))
        panels = [] if location.spread else _panels(view, top, bottom)
        for i, (px0, px1) in enumerate(panels or [(x0, x1)]):
            regions.append(
                Region(
                    page=number,
                    bbox=(round(px0, 2), round(top, 2), round(px1, 2), round(bottom, 2)),
                    title_bottom=title.bbox[3] if title is not None and i == 0 else None,
                    half=half if location.spread else ("right" if i else None),
                    title_top=title.bbox[1] if title is not None and i == 0 else None,
                )
            )
    return regions


def _panels(view: PageView, top: float, bottom: float) -> list[tuple[float, float]]:
    """Two side-by-side panels of one statement on a landscape page, or [] for a single table.

    Both must hold: figures that end before the middle (the left panel's value columns), and on
    the right a second label column starting just past the middle with its own figures further
    right. A single wide table (labels left, figures right of the middle) has no figures ending
    before the middle, so it is never split."""
    if view.width / view.height <= LANDSCAPE:
        return []
    mid = view.width / 2
    words = [(w.text.strip(), box) for w, box in view.words if top <= box[1] <= bottom]
    left_figures = [b for t, b in words if _NUMBER.match(t) and view.width * 0.2 < b[2] < mid]
    right_figures = [b for t, b in words if _NUMBER.match(t) and b[0] > mid + view.width * 0.12]
    right_labels = [
        line for line in view.lines
        if top <= line.bbox[1] <= bottom and mid <= line.bbox[0] < mid + view.width * 0.12
        and _LABEL.match(line.text.strip())
    ]  # fmt: skip
    if len(left_figures) >= 3 and len(right_figures) >= 3 and len(right_labels) >= 3:
        return [(0.0, mid), (mid, view.width)]
    return []


def _headings(view: PageView) -> Sequence[tuple[VisualLine, StatementType, bool]]:
    """Statement titles anywhere on the page, styled as headings (large or bold)."""
    median = view.median_size or 0.0
    out = []
    for line in view.lines:
        if not (line.line.bold or line.line.size >= TITLE_SIZE_RATIO * median):
            continue
        match = match_title(line.text)
        if match is not None:
            out.append((line, match.statement_type, match.continued))
    return out
