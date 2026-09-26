"""Digital-born score (EXTRACTION section 0).

A page passes when it has at least 200 extractable characters: non-whitespace characters that are
not replacement glyphs (U+FFFD, which MuPDF emits when a font has no Unicode mapping). The document
is digitally born when at least 90 % of its pages pass. Both thresholds are the initial values in
EXTRACTION section 0; change them there first, with evidence from the goldens.

Below the threshold the pipeline raises `not_digitally_born` and OCR-derived values are capped
below the publication threshold (M2.5). This module only measures.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from finintel.parse.text_layer import TextLayer

MIN_EXTRACTABLE_CHARS = 200
MIN_PASSING_PAGE_SHARE = 0.9


class DigitalBornScore(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_extractable_chars: int
    min_passing_page_share: float
    pages_total: int
    pages_passing: int
    passing_page_share: float
    #: Share of all extracted non-whitespace characters that are real glyphs (diagnostic).
    glyph_share: float | None
    failing_pages: tuple[int, ...]
    is_digitally_born: bool


def score_digital_born(
    text_layer: TextLayer,
    *,
    min_chars: int = MIN_EXTRACTABLE_CHARS,
    min_share: float = MIN_PASSING_PAGE_SHARE,
) -> DigitalBornScore:
    failing = []
    chars = replacement = 0
    for page in text_layer.pages:
        chars += page.char_count
        replacement += page.replacement_char_count
        if page.char_count - page.replacement_char_count < min_chars:
            failing.append(page.page)
    total = text_layer.page_count
    passing = total - len(failing)
    share = passing / total if total else 0.0
    return DigitalBornScore(
        min_extractable_chars=min_chars,
        min_passing_page_share=min_share,
        pages_total=total,
        pages_passing=passing,
        passing_page_share=round(share, 4),
        glyph_share=round((chars - replacement) / chars, 4) if chars else None,
        failing_pages=tuple(failing),
        is_digitally_born=share >= min_share,
    )
