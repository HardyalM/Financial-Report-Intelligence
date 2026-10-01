"""V6 advice lexicon and V7 direction consistency (RAG section 4.4)."""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping

from finintel.commentary.render import PLACEHOLDER, TruthEntry
from finintel.commentary.validators.text import blank_verified_quotes

ADVICE = re.compile(
    r"\b(?:buy|buys|sell|sells|hold|holds|recommend|recommends|recommended|recommendation|"
    r"undervalued|overvalued|target prices?|attractive investment|should invest)\b",
    re.IGNORECASE,
)
_UP_TEXT = """
improved improve improves improving improvement rose rise rises risen rising
increased increase increases increasing grew grow grows grown growing higher
strengthened strengthening expanded climbed gained
"""
UP = frozenset(_UP_TEXT.split())
_DOWN_TEXT = """
fell fall falls fallen falling declined decline declines declining decreased
decrease decreases decreasing weakened weakening lower dropped drop contracted
deteriorated deterioration slipped eroded
"""
DOWN = frozenset(_DOWN_TEXT.split())
_WORD = re.compile(r"[A-Za-z]+")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def advice_terms(template: str, verified_quotes: Collection[str]) -> list[str]:
    text = blank_verified_quotes(PLACEHOLDER.sub(" ", template), list(verified_quotes))
    return [m.group(0) for m in ADVICE.finditer(text)]


def direction_violations(
    template: str, verified_quotes: Collection[str], truth: Mapping[str, TruthEntry]
) -> list[str]:
    """Each direction word is paired with the nearest placeholder in its sentence and must agree
    with that placeholder's provided direction. A placeholder with no direction (or a flat one)
    cannot support a direction word, because the model would be inferring a comparison."""
    text = blank_verified_quotes(template, list(verified_quotes))
    problems: list[str] = []
    offset = 0
    for sentence in _SENTENCE_END.split(text):
        start = text.index(sentence, offset)
        offset = start + len(sentence)
        marks = [(m.start(), m.end(), m.group(1)) for m in PLACEHOLDER.finditer(sentence)]
        if not marks:
            continue
        for word in _WORD.finditer(sentence):
            w = word.group(0).lower()
            said = "up" if w in UP else "down" if w in DOWN else None
            if said is None:
                continue
            nearest = min(
                marks, key=lambda p: min(abs(word.start() - p[1]), abs(p[0] - word.end()))
            )
            entry = truth.get(nearest[2])
            if entry is None:
                continue  # an unknown placeholder is V4's finding
            if entry.direction != said:
                provided = entry.direction or "no direction"
                problems.append(f"'{w}' next to {{{{{nearest[2]}}}}} which has {provided}")
    return problems
