"""Where a located statement sits on each of its pages (EXTRACTION section 2).

A statement region runs from below its title down to the next statement heading on the page, or
to the page foot. Headings are found anywhere on the page, not only in the title region: Unilever
prints its statement of comprehensive income under the income statement on the same page, and
"Net profit" appears in both. On a two-page spread the region is the half holding the statement.

Regions are in unrotated page space. Rotated statement pages are not supported in v1: the
builder records that plainly instead of guessing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from finintel.locate.models import StatementLocation, StatementType
from finintel.locate.signals import TITLE_SIZE_RATIO, PageView, VisualLine
from finintel.locate.titles import match_title
from finintel.parse.engines.base import BBox
from finintel.parse.text_layer import TextLayer

FOOTER_MARGIN = 0.06  # folios and running footers are not table rows


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
        regions.append(
            Region(
                page=number,
                bbox=(round(x0, 2), round(top, 2), round(x1, 2), round(bottom, 2)),
                title_bottom=title.bbox[3] if title is not None else None,
                half=half if location.spread else None,
                title_top=title.bbox[1] if title is not None else None,
            )
        )
    return regions


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
