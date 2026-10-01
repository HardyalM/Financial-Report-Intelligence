"""Table regions on narrative pages (RAG section 1.2): text inside one never enters prose.

The numeric-density detector runs on every page from the text layer alone, so it works with no
Azure response and no PDF handle. A run of three or more consecutive printed rows qualifies when
at least half its rows carry two or more numeric tokens and at least two columns of numbers line
up on their right edges (within 3 pt) across the run. Rows are then extended to the full row width,
so the labels belong to the table too.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from finintel.locate.signals import NUMERIC, PageView
from finintel.parse.text_layer import BBox

#: Figures as narrative tables print them: 9,400  (1.4)  14.5%  -1.8%  EUR 0.6bn  2.5x  a dash.
TABLE_NUMERIC = re.compile(
    r"^[(\-\u2013\u2212+]?[\u00a3$\u20ac]?\d[\d,]*(?:\.\d+)?(?:%|bn|m|pts?|x|pp)?\)?[*\u2020\u2021]?$"
    r"|^[\-\u2013\u2014]$"
)
NUMERIC_SHARE = 0.25  # an external (ruled) region counts as a table only if this share is figures

MIN_ROWS = 2
MIN_NUMERIC_TOKENS = 2
ROW_SHARE = 0.5
ALIGN = 3.0  # pt
MIN_ALIGNED_COLUMNS = 2
MAX_GAP_ROWS = 1  # a sub-heading or blank row inside a table does not end it


@dataclass(frozen=True)
class TableRegion:
    page: int
    bbox: BBox  # display-space points

    def contains(self, box: BBox, inside: float = 0.5) -> bool:
        """True if at least `inside` of the box's area lies in the region."""
        x0, y0 = max(box[0], self.bbox[0]), max(box[1], self.bbox[1])
        x1, y1 = min(box[2], self.bbox[2]), min(box[3], self.bbox[3])
        area = max(box[2] - box[0], 0.01) * max(box[3] - box[1], 0.01)
        return max(x1 - x0, 0.0) * max(y1 - y0, 0.0) >= inside * area


def table_regions(view: PageView) -> list[TableRegion]:
    rows = view.row_boxes
    numeric_rows = [sum(1 for w, _ in row if _figure(w.text)) >= MIN_NUMERIC_TOKENS for row in rows]
    regions: list[TableRegion] = []
    i = 0
    while i < len(rows):
        if not numeric_rows[i]:
            i += 1
            continue
        j, last, gap = i, i, 0
        while j + 1 < len(rows) and gap <= MAX_GAP_ROWS:
            j += 1
            if numeric_rows[j]:
                last, gap = j, 0
            else:
                gap += 1
        run = range(i, last + 1)
        if _is_table(rows, numeric_rows, run):
            boxes = [b for k in run for _, b in rows[k]]
            regions.append(
                TableRegion(
                    view.page.page,
                    (
                        round(min(b[0] for b in boxes), 2),
                        round(min(b[1] for b in boxes), 2),
                        round(max(b[2] for b in boxes), 2),
                        round(max(b[3] for b in boxes), 2),
                    ),
                )
            )
        i = last + 1
    return regions


def _is_table(rows: tuple, numeric_rows: list[bool], run: range) -> bool:  # type: ignore[type-arg]
    if len(run) < MIN_ROWS or sum(numeric_rows[k] for k in run) < max(
        MIN_ROWS, ROW_SHARE * len(run)
    ):
        return False
    edges = sorted(b[2] for k in run if numeric_rows[k] for w, b in rows[k] if _figure(w.text))
    clusters: list[list[float]] = []
    for edge in edges:
        if clusters and edge - clusters[-1][-1] <= ALIGN:
            clusters[-1].append(edge)
        else:
            clusters.append([edge])
    support = max(MIN_ROWS, round(ROW_SHARE * sum(numeric_rows[k] for k in run)))
    return sum(1 for c in clusters if len(c) >= support) >= MIN_ALIGNED_COLUMNS


def _figure(text: str) -> bool:
    return bool(TABLE_NUMERIC.match(text) or NUMERIC.match(text))


def numeric_share(view: PageView, box: BBox) -> float:
    """Share of the words centred in `box` that are figures."""
    words = [
        w
        for w, b in view.words
        if box[0] <= (b[0] + b[2]) / 2 <= box[2] and box[1] <= (b[1] + b[3]) / 2 <= box[3]
    ]
    return sum(_figure(w.text) for w in words) / len(words) if words else 0.0


def merge_regions(regions: Sequence[TableRegion]) -> list[TableRegion]:
    """Overlapping regions on a page become one (a detector and a ruled-table finder agree)."""
    out: list[TableRegion] = []
    for region in sorted(regions, key=lambda r: (r.page, r.bbox[1], r.bbox[0])):
        for i, prev in enumerate(out):
            a, b = prev.bbox, region.bbox
            if (
                prev.page == region.page
                and min(a[2], b[2]) > max(a[0], b[0])
                and min(a[3], b[3]) > max(a[1], b[1])
            ):
                out[i] = TableRegion(
                    prev.page, (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))
                )
                break
        else:
            out.append(region)
    return out


def page_table_regions(view: PageView, external: Sequence[BBox] = ()) -> list[TableRegion]:
    """Density regions plus external (ruled) regions that are mostly figures, merged."""
    found = table_regions(view)
    found += [
        TableRegion(view.page.page, box)
        for box in external
        if numeric_share(view, box) >= NUMERIC_SHARE
    ]
    return merge_regions(found)
