"""Extractive mode (RAG section 4.5): no model. The top chunks' opening sentences, verbatim.

Each paragraph is a verbatim quotation with its citation. It goes through the same validators as
generated text, so a quotation that cannot be cited is not shown. Numbers appear only inside the
verbatim quotation (exempt as in T12) or in the code-rendered snapshot.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from finintel.commentary.render import TruthEntry
from finintel.commentary.validators import finalize, validate_output
from finintel.contracts.commentary import Paragraph
from finintel.narrative.models import Chunk

LABEL = "Extractive summary: no generated text"
CHUNKS_PER_TOPIC = 3
MIN_WORDS, MAX_WORDS = 5, 60
SHORT_SENTENCE_WORDS = 8
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"])")


def _quotable(sentence: str) -> bool:
    """A whole printed sentence: capitalised, terminated, one line, no bullets or table residue."""
    words = len(sentence.split())
    return (
        MIN_WORDS <= words <= MAX_WORDS
        and sentence[:1].isupper()
        and sentence.endswith((".", "!", "?"))
        and not any(ch in sentence for ch in ('"', "\u201c", "\u201d", "\n", "\u25a0", "\u2022"))
        and "million"
        not in sentence.lower().split("\u20ac")[-1][:12]  # "EUR million" header debris
    )


def opening_sentences(text: str) -> str | None:
    """The first quotable sentence, plus the next when the first is short. None if none is."""
    sentences = [s.strip() for s in _SENTENCE.split(text.strip())]
    for i, sentence in enumerate(sentences):
        if not _quotable(sentence):
            continue
        if len(sentence.split()) < SHORT_SENTENCE_WORDS and i + 1 < len(sentences):
            joined = f"{sentence} {sentences[i + 1]}"
            if _quotable(joined):
                return joined
        return sentence
    return None


def extractive_paragraphs(
    topic: str,
    chunk_ids: Sequence[str],
    chunks: Mapping[str, Chunk],
    truth: Mapping[str, TruthEntry],
    page_labels: Mapping[int, str] | None = None,
) -> list[Paragraph]:
    paragraphs: list[dict[str, Any]] = []
    for cid in chunk_ids:
        if len(paragraphs) == CHUNKS_PER_TOPIC:
            break
        sentence = opening_sentences(chunks[cid].text)
        if sentence is not None:
            paragraphs.append(
                {"template": f"“{sentence}”", "citations": [{"chunk_id": cid, "quote": sentence}]}
            )
    raw = {"topic": topic, "status": "ok", "reason": None, "paragraphs": paragraphs}
    if not paragraphs:
        return []
    report = validate_output(
        raw, topic=topic, evidence=chunks, truth=truth, page_labels=page_labels
    )
    return finalize(report, retried=False)[2]
