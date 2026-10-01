"""V5: no naked numbers (RAG section 4.4, ADR-003).

After removing placeholders and quotation-marked spans copied from verified quotes, no number may
remain, in digits or in words. A false positive costs a paragraph; a false negative costs trust.
"""

from __future__ import annotations

import re
from collections.abc import Collection

from finintel.commentary.render import PLACEHOLDER
from finintel.commentary.validators.text import blank_verified_quotes

_UNITS_TEXT = """
zero one two three four five six seven eight nine ten eleven twelve thirteen
fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty
seventy eighty ninety
"""
_UNITS = _UNITS_TEXT.split()
_CARDINAL = re.compile(
    r"\b(?:"
    + "|".join(_UNITS)
    + r"|hundreds?|thousands?|millions?|billions?|trillions?|dozens?)\b",
    re.IGNORECASE,
)
_ONE_OF = re.compile(r"\bone\s+of\b", re.IGNORECASE)
_MULTIPLIER = re.compile(
    r"\b(?:half|halves|halved|double[ds]?|doubling|twice|triple[ds]?|treble[ds]?)\b", re.IGNORECASE
)
_FRACTION = re.compile(r"\ba\s+(?:third|quarter|fifth|sixth|eighth|tenth)\b", re.IGNORECASE)
_QUARTER = re.compile(r"\bquarters?\b", re.IGNORECASE)
_ORDINAL_BEFORE_QUARTER = {"first", "second", "third", "fourth"}
_DIGITS = re.compile(r"\d[\d,.]*")
_NOTE = re.compile(r"\bnotes?\s+$", re.IGNORECASE)


def naked_numbers(
    template: str,
    verified_quotes: Collection[str],
    *,
    allowed_years: Collection[str] = (),
    note_numbers: Collection[str] = (),
) -> list[str]:
    """Every number the paragraph states on its own. Empty means the paragraph is clean."""
    text = PLACEHOLDER.sub(" ", template)
    text = blank_verified_quotes(text, list(verified_quotes))
    found: list[str] = []
    for m in _DIGITS.finditer(text):
        token = m.group(0).rstrip(".,")
        if token in allowed_years:
            continue
        if token in note_numbers and _NOTE.search(text[: m.start()]):
            continue
        found.append(token)
    one_of = {m.start() for m in _ONE_OF.finditer(text)}
    for m in _CARDINAL.finditer(text):
        if m.group(0).lower() == "one" and m.start() in one_of:
            continue
        found.append(m.group(0))
    found.extend(m.group(0) for m in _MULTIPLIER.finditer(text))
    found.extend(m.group(0) for m in _FRACTION.finditer(text))
    for m in _QUARTER.finditer(text):
        before = text[: m.start()].split()
        if before and before[-1].lower() in _ORDINAL_BEFORE_QUARTER:
            continue
        if _FRACTION.match(text, max(0, m.start() - 2)):  # already counted as "a quarter"
            continue
        found.append(m.group(0))
    return found
