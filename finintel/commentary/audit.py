"""E4 audit of what is *displayed*: re-checks the final commentary independently of the generator.

The generator already validates. This module re-derives the checks from the stored output and the
chunk texts with simple string operations, so a bug in the validation path cannot hide a bad
paragraph from the gate. Every count must be zero for a run to pass (EVAL E4).
"""

from __future__ import annotations

from collections.abc import Collection, Iterator, Mapping
from typing import Any

from finintel.commentary.render import PLACEHOLDER, TruthEntry
from finintel.commentary.validators import (
    advice_terms,
    direction_violations,
    mismatched_placeholders,
    naked_numbers,
)
from finintel.commentary.validators.text import simple
from finintel.contracts.commentary import Commentary, Paragraph
from finintel.narrative.models import Chunk


def displayed(commentary: Commentary) -> Iterator[Paragraph]:
    for _, paragraph in displayed_ids(commentary):
        yield paragraph


def displayed_ids(commentary: Commentary) -> Iterator[tuple[str, Paragraph]]:
    """Every displayed paragraph with a stable id: `<topic>:<n>`, `executive_summary:<n>`."""
    for topic in commentary.topics:
        for n, paragraph in enumerate(topic.paragraphs):
            yield f"{topic.topic}:{n}", paragraph
    for n, bullet in enumerate(commentary.executive_summary.bullets):
        yield f"executive_summary:{n}", bullet


def audit_commentary(
    commentary: Commentary,
    chunks: Mapping[str, Chunk],
    truth: Mapping[str, TruthEntry],
    *,
    allowed_years: Collection[str] = (),
) -> dict[str, Any]:
    unverified = naked = advice = unknown = direction = no_citation = mismatched = total = 0
    for para in displayed(commentary):
        total += 1
        if not para.citations:
            no_citation += 1
        for cite in para.citations:
            if not _verified(cite, chunks):
                unverified += 1
        quotes = [c.quote for c in para.citations]
        notes = {c.note_number for c in para.citations if c.note_number}
        if naked_numbers(para.template, quotes, allowed_years=allowed_years, note_numbers=notes):
            naked += 1
        if advice_terms(para.template, quotes):
            advice += 1
        if any(m.group(1) not in truth for m in PLACEHOLDER.finditer(para.template)):
            unknown += 1
        if direction_violations(para.template, quotes, truth):
            direction += 1
        if mismatched_placeholders(para.template, truth):
            mismatched += 1
    return {
        "displayed_paragraphs": total,
        "displayed_unverified_citations": unverified,
        "displayed_naked_numbers": naked,
        "displayed_advice": advice,
        "displayed_unknown_placeholders": unknown,
        "displayed_direction_violations": direction,
        "displayed_mismatched_placeholders": mismatched,
        "displayed_without_citation": no_citation,
    }


def _verified(cite: Any, chunks: Mapping[str, Chunk]) -> bool:
    """The quote is the text at the stated offsets, and its pages are the chunk's own."""
    chunk = chunks.get(cite.chunk_id)
    if chunk is None:
        return False
    start, end = cite.char_start - chunk.char_start, cite.char_end - chunk.char_start
    if not 0 <= start < end <= len(chunk.text):
        return False
    if simple(chunk.text[start:end]) != simple(cite.quote):
        return False
    return bool(cite.page == chunk.page_at(start) and cite.page_end == chunk.page_at(end - 1))
