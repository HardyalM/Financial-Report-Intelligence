"""A page as ordered blocks: paragraph, heading, table or footnote (RAG sections 1.1-2).

Reading order is PyMuPDF's block order (it follows the content stream, which keeps columns
together on typeset reports). Furniture lines are dropped, table rows are pulled out whole, and
what is left is grouped one paragraph per PyMuPDF block (split where a line gap says a new
paragraph starts). Headings are short blocks that are larger than body text, or bold, or a note
heading. Footnotes are small-print blocks in the lower part of the page that start with a marker.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import median

from finintel.locate.signals import PageView, collapse
from finintel.narrative.margins import is_furniture
from finintel.narrative.sections import (
    HEADING_SIZE_RATIO,
    MAX_BOLD_ONLY_WORDS,
    is_heading_text,
    note_heading,
)
from finintel.narrative.tables import TableRegion, page_table_regions
from finintel.parse.text_layer import BBox, PageText, TextLayer

PARAGRAPH_GAP = 1.0  # x font size between lines: more starts a new paragraph
STYLE_CHANGE = 0.12  # a size change this large, or a bold switch, starts a new block (a heading)
FOOTNOTE_SIZE = 0.85  # x body size
FOOTNOTE_ZONE = 0.70  # lower 30 % of the page
_MARKER = re.compile(r"^(?P<m>\(?[a-z0-9*†‡]{1,2}\)|[*†‡]|\d{1,2})\s+\S")


@dataclass(frozen=True)
class LineRef:
    text: str
    page: int
    bbox: BBox  # display space


@dataclass
class Block:
    kind: str  # paragraph, heading, table, footnote
    page: int
    lines: list[LineRef] = field(default_factory=list)
    size: float = 0.0
    bold: bool = False
    level: int = 0  # headings: 1 (largest) to 3
    marker: str | None = None  # footnotes

    @property
    def text(self) -> str:
        return collapse(" ".join(line.text for line in self.lines))


def body_size(layer: TextLayer) -> float:
    """Median word size over the document: the body text size."""
    sizes = [w.size for p in layer.pages for w in p.words if w.size > 0]
    return float(median(sizes)) if sizes else 9.0


def page_blocks(
    page: PageText,
    repeated: frozenset[str],
    body: float,
    external_tables: Sequence[BBox] = (),
) -> tuple[list[Block], list[TableRegion]]:
    view = PageView(page)
    regions = page_table_regions(view, external_tables)
    blocks: list[Block] = []
    table_blocks: dict[int, Block] = {}
    current: Block | None = None
    last_block: int | None = None
    last_size, last_bold = 0.0, False
    last_bottom = 0.0
    for line in page.lines:
        box = page.visual_bbox(line.bbox)
        text = collapse(line.text)
        if not text or is_furniture(text, box[1], box[3], view.height, repeated):
            continue
        hit = next((k for k, r in enumerate(regions) if r.contains(box)), None)
        if hit is not None:
            if hit not in table_blocks:
                table_blocks[hit] = Block("table", page.page)
                blocks.append(table_blocks[hit])
                current = None
            continue
        ref = LineRef(text, page.page, box)
        new_para = (
            current is None
            or current.kind != "paragraph"
            or line.block != last_block
            or box[1] - last_bottom > PARAGRAPH_GAP * max(line.size, 1.0)
            or abs(line.size - last_size) > STYLE_CHANGE * max(last_size, 1.0)
            or line.bold != last_bold
        )
        if new_para:
            current = Block("paragraph", page.page, size=line.size, bold=line.bold)
            blocks.append(current)
        assert current is not None
        current.lines.append(ref)
        current.size = max(current.size, line.size)
        current.bold = current.bold and line.bold
        last_block, last_bottom = line.block, box[3]
        last_size, last_bold = line.size, line.bold
    for k, region in enumerate(regions):
        block = table_blocks.get(k)
        if block is not None:
            block.lines = [
                LineRef(collapse(" ".join(w.text for w, _ in row)), page.page, _row_box(row))
                for row in view.row_boxes
                if row and region.contains(_row_box(row), 0.6)
            ]
            block.size = body
    return [_classify(b, view, body) for b in blocks if b.lines], regions


def _row_box(row: tuple) -> BBox:  # type: ignore[type-arg]
    return (
        min(b[0] for _, b in row), min(b[1] for _, b in row),
        max(b[2] for _, b in row), max(b[3] for _, b in row),
    )  # fmt: skip


def _classify(block: Block, view: PageView, body: float) -> Block:
    if block.kind == "table":
        return block
    text = block.text
    top = block.lines[0].bbox[1]
    small = block.size <= FOOTNOTE_SIZE * body and top >= view.height * FOOTNOTE_ZONE
    marker = _MARKER.match(text)
    if small and marker:
        block.kind, block.marker = "footnote", marker.group("m")
        return block
    styled = block.size >= HEADING_SIZE_RATIO * body or block.bold
    larger = block.size >= HEADING_SIZE_RATIO * body
    words = len(text.split())
    short_enough = (
        larger or 2 <= words <= MAX_BOLD_ONLY_WORDS
    )  # a bold one-word line is a column label
    is_head = len(block.lines) <= 2 and is_heading_text(text) and (styled or note_heading(text))
    if is_head and short_enough and (styled or block.size >= body):
        block.kind = "heading"
        ratio = block.size / body if body else 1.0
        block.level = 1 if ratio >= 1.6 else 2 if ratio >= 1.3 else 3
    return block
