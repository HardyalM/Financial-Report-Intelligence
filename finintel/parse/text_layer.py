"""PyMuPDF text layer: the anchor of truth for characters (EXTRACTION section 0, ADR-001).

Every other engine is checked against this layer, so it records what is printed and where, and
nothing else: text is kept verbatim (no NFKC, no dehyphenation, ligatures preserved) and no number
is interpreted.

Conventions:
- `page` is the 1-based PDF page index (SCHEMA section 4.1), never the printed folio. The folio,
  when the PDF defines page labels, is `PageText.label`.
- Coordinates are PDF points in PyMuPDF page space: origin top-left, y grows downwards, on the
  unrotated page. `PageText.rotation` records any /Rotate so later stages can derotate.
- Words carry the (block, line) ids of PyMuPDF's reading-order blocks. Word, line and span come
  from one TextPage, so the ids agree across all three.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from statistics import median
from typing import Any

import pymupdf
from pydantic import BaseModel, ConfigDict

#: Bump when extracted fields or their meaning change. Part of every text-layer cache key.
TEXT_LAYER_VERSION = "1"
#: The extracting library and version. A PyMuPDF upgrade can change extraction, so it is part of
#: the cache key as well.
EXTRACTOR = f"pymupdf {pymupdf.VersionBind}"
REPLACEMENT_CHAR = "\ufffd"

# Verbatim text: keep whitespace and ligatures, clip to the media box. No dehyphenation.
_FLAGS = pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_PRESERVE_LIGATURES
_FLAGS |= pymupdf.TEXT_MEDIABOX_CLIP
_BOLD_FLAG = 16  # span flag bit 4 (MuPDF: font is bold)
_BOLD_NAME = re.compile(r"bold|black|heavy|semibold|demibold", re.IGNORECASE)
_RULE_MIN_LENGTH = 10.0  # pt; shorter strokes are glyph decorations, not table rules
_RULE_MAX_THICKNESS = 2.0  # pt; filled rectangles thinner than this act as rules

BBox = tuple[float, float, float, float]


def _r(value: float) -> float:
    """Round coordinates to 0.01 pt: far below print resolution, and stable across runs."""
    return round(float(value), 2)


def _bbox(values: Iterable[float]) -> BBox:
    x0, y0, x1, y1 = (_r(v) for v in values)
    return (x0, y0, x1, y1)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Word(_Frozen):
    """One whitespace-delimited word, exactly as printed."""

    text: str
    bbox: BBox
    block: int
    line: int
    font: str
    size: float
    bold: bool


class Line(_Frozen):
    """One PyMuPDF line: spans that share a baseline within a block."""

    block: int
    line: int
    bbox: BBox
    text: str
    size: float  # largest span size on the line
    bold: bool  # every non-blank span is bold


class Rule(_Frozen):
    """A horizontal ruling line (stroked line or thin filled rectangle). Drives row style."""

    x0: float
    x1: float
    y: float
    thickness: float


class PageText(_Frozen):
    """Text layer of one PDF page."""

    page: int
    label: str | None
    width: float
    height: float
    rotation: int
    words: tuple[Word, ...] = ()
    lines: tuple[Line, ...] = ()
    rules: tuple[Rule, ...] = ()
    char_count: int = 0  # non-whitespace characters, replacement glyphs included
    replacement_char_count: int = 0
    error: str | None = None  # set when the page could not be read; the page is then empty

    @property
    def text(self) -> str:
        """Page text in PyMuPDF reading order, one line per text line."""
        return "\n".join(line.text for line in self.lines)

    @property
    def median_word_size(self) -> float | None:
        return median(w.size for w in self.words) if self.words else None


class OutlineEntry(_Frozen):
    """One PDF bookmark. `page` is the 1-based target, or None when the bookmark has none."""

    level: int
    title: str
    page: int | None


class TextLayer(_Frozen):
    """The whole document's text layer."""

    version: str = TEXT_LAYER_VERSION
    extractor: str
    page_count: int
    has_page_labels: bool
    outline: tuple[OutlineEntry, ...]
    pages: tuple[PageText, ...]

    def page(self, number: int) -> PageText:
        """Return a page by 1-based PDF page index."""
        if not 1 <= number <= self.page_count:
            raise IndexError(f"page {number} outside 1..{self.page_count}")
        return self.pages[number - 1]

    def to_json(self) -> bytes:
        return self.model_dump_json().encode("utf-8")

    @classmethod
    def from_json(cls, data: bytes | str) -> TextLayer:
        return cls.model_validate_json(data)


def read_text_layer(pdf_path: Path) -> TextLayer:
    """Read the embedded text layer of a digitally born PDF.

    A page that fails to extract is recorded with `error` set and no words; the rest of the
    document is still read (ARCHITECTURE section 4, step 3: `page_unreadable`).
    """
    with pymupdf.open(pdf_path) as doc:
        if doc.needs_pass:
            raise ValueError(f"{pdf_path.name} is password-protected; ingest rejects it first")
        pages = tuple(_read_page_safely(doc, index) for index in range(doc.page_count))
        return TextLayer(
            extractor=EXTRACTOR,
            page_count=doc.page_count,
            has_page_labels=bool(doc.get_page_labels()),
            outline=_outline(doc.get_toc(simple=True)),
            pages=pages,
        )


def render_page_png(pdf_path: Path, page: int, dpi: int = 50) -> bytes:
    """Render one page (1-based) to PNG bytes, for inspection thumbnails."""
    with pymupdf.open(pdf_path) as doc:
        pixmap = doc[page - 1].get_pixmap(dpi=dpi, alpha=False)
        png: bytes = pixmap.tobytes("png")
        return png


def _outline(toc: Sequence[Sequence[Any]]) -> tuple[OutlineEntry, ...]:
    entries = []
    for level, title, target in (entry[:3] for entry in toc):
        page = int(target) if isinstance(target, int) and target >= 1 else None
        entries.append(OutlineEntry(level=int(level), title=str(title).strip(), page=page))
    return tuple(entries)


def _read_page_safely(doc: pymupdf.Document, index: int) -> PageText:
    page = doc[index]
    label = page.get_label() or None
    rect = page.rect
    try:
        return _read_page(page, index + 1, label)
    except Exception as exc:  # MuPDF raises several types for damaged content streams
        return PageText(
            page=index + 1,
            label=label,
            width=_r(rect.width),
            height=_r(rect.height),
            rotation=int(page.rotation),
            error=f"page_unreadable: {type(exc).__name__}",
        )


def _read_page(page: pymupdf.Page, number: int, label: str | None) -> PageText:
    textpage = page.get_textpage(flags=_FLAGS)
    raw_words = page.get_text("words", textpage=textpage)
    layout = page.get_text("dict", textpage=textpage)
    blocks: list[dict[str, Any]] = layout["blocks"]

    words = tuple(_word(raw, blocks) for raw in raw_words)
    lines = tuple(_lines(blocks))
    rect = page.rect
    return PageText(
        page=number,
        label=label,
        width=_r(rect.width),
        height=_r(rect.height),
        rotation=int(page.rotation),
        words=words,
        lines=lines,
        rules=_rules(page),
        char_count=sum(len(w.text) for w in words),
        replacement_char_count=sum(w.text.count(REPLACEMENT_CHAR) for w in words),
    )


def _word(raw: Sequence[Any], blocks: list[dict[str, Any]]) -> Word:
    x0, y0, x1, y1, text, block, line = raw[:7]
    span = _span_for(blocks[block]["lines"][line]["spans"], float(x0), float(x1))
    font = str(span.get("font", ""))
    return Word(
        text=str(text),
        bbox=_bbox((x0, y0, x1, y1)),
        block=int(block),
        line=int(line),
        font=font,
        size=_r(span.get("size", 0.0)),
        bold=_is_bold(font, int(span.get("flags", 0))),
    )


def _span_for(spans: list[dict[str, Any]], x0: float, x1: float) -> dict[str, Any]:
    """The span overlapping the word most (a word can straddle spans, e.g. a superscript)."""

    def overlap(span: dict[str, Any]) -> float:
        sx0, _, sx1, _ = span["bbox"]
        return min(x1, float(sx1)) - max(x0, float(sx0))

    candidates = [s for s in spans if s["text"].strip()] or spans
    return max(candidates, key=overlap) if candidates else {}


def _is_bold(font: str, flags: int) -> bool:
    return bool(flags & _BOLD_FLAG) or bool(_BOLD_NAME.search(font))


def _lines(blocks: list[dict[str, Any]]) -> Iterable[Line]:
    for block_no, block in enumerate(blocks):
        for line_no, line in enumerate(block.get("lines", ())):
            spans = line["spans"]
            text = "".join(s["text"] for s in spans)
            if not text.strip():
                continue
            printed = [s for s in spans if s["text"].strip()]
            yield Line(
                block=block_no,
                line=line_no,
                bbox=_bbox(line["bbox"]),
                text=text,
                size=_r(max(s["size"] for s in printed)),
                bold=all(_is_bold(s["font"], s["flags"]) for s in printed),
            )


def _rules(page: pymupdf.Page) -> tuple[Rule, ...]:
    found: set[Rule] = set()
    for path in page.get_cdrawings():
        stroke = float(path.get("width") or 0.0)
        for item in path.get("items", ()):
            kind = item[0]
            if kind == "l":
                (ax, ay), (bx, by) = item[1], item[2]
                if abs(ay - by) <= 0.5 and abs(bx - ax) >= _RULE_MIN_LENGTH:
                    found.add(_rule(min(ax, bx), max(ax, bx), (ay + by) / 2, stroke))
            elif kind == "re":
                x0, y0, x1, y1 = item[1]
                height, width = abs(y1 - y0), abs(x1 - x0)
                if height <= _RULE_MAX_THICKNESS and width >= _RULE_MIN_LENGTH:
                    found.add(_rule(min(x0, x1), max(x0, x1), (y0 + y1) / 2, max(height, stroke)))
    return tuple(sorted(found, key=lambda r: (r.y, r.x0, r.x1, r.thickness)))


def _rule(x0: float, x1: float, y: float, thickness: float) -> Rule:
    return Rule(x0=_r(x0), x1=_r(x1), y=_r(y), thickness=_r(thickness))
