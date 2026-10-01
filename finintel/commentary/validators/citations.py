"""V3: verify a quote against its chunk and build the Citation (ADR-003, RAG section 5).

The model supplied `{chunk_id, quote}`. Everything else, page included, is computed here from the
chunk's character-to-page map and line boxes. A model-supplied page is never read.
"""

from __future__ import annotations

from collections.abc import Mapping

from finintel.commentary.validators.text import locate_quote, word_count
from finintel.contracts.commentary import Citation
from finintel.narrative.models import Chunk

MIN_QUOTE_WORDS = 5
MAX_QUOTE_WORDS = 60


class QuoteError(Exception):
    """The quote cannot be cited. `code` is the reason recorded with the removed citation."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def build_citation(
    chunk: Chunk,
    quote: str,
    citation_id: str,
    page_labels: Mapping[int, str] | None = None,
) -> Citation:
    words = word_count(quote)
    if not MIN_QUOTE_WORDS <= words <= MAX_QUOTE_WORDS:
        raise QuoteError(f"quote_length:{words}_words")
    found = locate_quote(chunk.text, quote)
    if found is None:
        raise QuoteError("quote_not_in_chunk")
    page = chunk.page_at(found.start)
    page_end = chunk.page_at(found.end - 1)
    labels = page_labels or {}
    return Citation(
        citation_id=citation_id,
        chunk_id=chunk.chunk_id,
        quote=quote.strip(),
        match="exact" if found.exact else "normalised",
        char_start=chunk.char_start + found.start,
        char_end=chunk.char_start + found.end,
        page=page,
        page_end=page_end,
        page_label=labels.get(page),
        section=chunk.section_id,
        heading_path=list(chunk.heading_path),
        note_number=chunk.note_number,
        is_footnote=chunk.is_footnote,
        bbox=_boxes(chunk, found.start, found.end),
    )


def _boxes(chunk: Chunk, start: int, end: int) -> list[list[float]]:
    """One [page, x0, y0, x1, y1] per page: the union of the lines the quote touches."""
    lines = sorted(chunk.line_boxes, key=lambda line: line.offset)
    union: dict[int, list[float]] = {}
    for i, line in enumerate(lines):
        line_end = lines[i + 1].offset if i + 1 < len(lines) else len(chunk.text)
        if line.offset >= end or line_end <= start:
            continue
        x0, y0, x1, y1 = line.bbox
        box = union.setdefault(line.page, [x0, y0, x1, y1])
        box[:] = [min(box[0], x0), min(box[1], y0), max(box[2], x1), max(box[3], y1)]
    return [[float(page), *box] for page, box in sorted(union.items())]
