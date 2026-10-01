"""Text normalisation with an offset map, and quote location (ADR-003, V3).

Quotes are matched after normalising whitespace, curly vs straight quotation marks, dash variants,
ligatures and hyphenation at line ends. Every normalised character remembers which character of
the original it came from, so a match gives exact offsets into the chunk text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LIGATURES = {
    "\ufb01": "fi", "\ufb02": "fl", "\ufb00": "ff", "\ufb03": "ffi", "\ufb04": "ffl",
    "\ufb05": "st", "\ufb06": "st",
}  # fmt: skip
SINGLE = dict.fromkeys("\u2018\u2019\u201a\u2032", "'")
DOUBLE = dict.fromkeys("\u201c\u201d\u201e\u2033", '"')
DASHES = dict.fromkeys("\u2010\u2011\u2012\u2013\u2014\u2015\u2212", "-")
DROPPED = {"\u00ad", "\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"}  # soft hyphen, zero-width
#: A hyphen at a line end: letter, hyphen, whitespace, lowercase letter ("supply- chain").
_LINE_END_HYPHEN = re.compile(r"(?<=[A-Za-z])[-\u2010\u2011]\s+(?=[a-z])")
_QUOTED = re.compile(r'"([^"]*)"|\u201c([^\u201d]*)\u201d')


def normalise(text: str, *, join_hyphen: bool = True) -> tuple[str, list[int]]:
    """Normalised text and, per output character, the index of its source character.

    `join_hyphen` removes a line-end hyphen with its break ("sup- ply" -> "supply"); otherwise only
    the break goes ("supply- chain" -> "supply-chain"), which is right for real compounds.
    """
    skip: set[int] = set()
    for m in _LINE_END_HYPHEN.finditer(text):
        skip.update(range(m.start() if join_hyphen else m.start() + 1, m.end()))
    out: list[str] = []
    index: list[int] = []
    for i, ch in enumerate(text):
        if i in skip or ch in DROPPED:
            continue
        if ch.isspace():
            if out and out[-1] == " ":
                continue
            out.append(" ")
            index.append(i)
            continue
        replacement = LIGATURES.get(ch) or SINGLE.get(ch) or DOUBLE.get(ch) or DASHES.get(ch) or ch
        for r in replacement:
            out.append(r)
            index.append(i)
    return "".join(out), index


def simple(text: str) -> str:
    """Normalised string only, whitespace trimmed."""
    return normalise(text, join_hyphen=False)[0].strip()


@dataclass(frozen=True)
class QuoteMatch:
    start: int  # offsets in the chunk text, end exclusive
    end: int
    exact: bool  # the quote is a literal substring (before any normalisation)


def word_count(quote: str) -> int:
    return len(quote.split())


def locate_quote(chunk_text: str, quote: str) -> QuoteMatch | None:
    """Where `quote` sits in `chunk_text`, or None. Offsets index the original chunk text."""
    q = quote.strip()
    if not q:
        return None
    exact_at = chunk_text.find(q)
    if exact_at >= 0:
        return QuoteMatch(exact_at, exact_at + len(q), True)
    for join in (True, False):
        norm_chunk, index = normalise(chunk_text, join_hyphen=join)
        norm_quote = normalise(q, join_hyphen=join)[0].strip()
        if not norm_quote:
            continue
        at = norm_chunk.find(norm_quote)
        if at >= 0:
            return QuoteMatch(index[at], index[at + len(norm_quote) - 1] + 1, False)
    return None


def blank_verified_quotes(text: str, verified_quotes: list[str]) -> str:
    """Blank out quotation-marked spans that are substrings of a verified quote (T12).

    Only text the model put between double quotation marks *and* that appears in a quote the code
    verified is exempt from the number, advice and direction checks. Anything else stays.
    """
    normalised = [simple(q) for q in verified_quotes]

    def sub(m: re.Match[str]) -> str:
        inner = m.group(1) if m.group(1) is not None else m.group(2)
        span = simple(inner)
        if span and any(span in q for q in normalised):
            return " " * len(m.group(0))
        return m.group(0)

    return _QUOTED.sub(sub, text)
