"""Pages that are never statement candidates, whatever their score (EXTRACTION section 1.2).

The same figures, or adjusted versions of them, appear on these pages. Excluding them is the main
defence against APM contamination. Evidence is the page's own headers (chrome excluded) and the
PDF bookmark section it sits in.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from finintel.locate.signals import normalise

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (reason, re.compile(pattern))
    for reason, pattern in (
        ("highlights or KPI page", r"\b(?:highlights|key performance indicators|kpis?)\b"),
        (
            "financial review",
            r"\b(?:financial review|chief financial officer|cfo'?s? (?:review|report))\b",
        ),
        ("multi-year summary", r"\b(?:five|ten|\d+)[- ]year (?:summary|record|review|history)\b"),
        ("multi-year summary", r"\bhistorical (?:summary|record)\b"),
        ("APM reconciliation", r"\b(?:alternative performance measures?|non-gaap|apms?)\b"),
        ("segment note", r"\bsegment(?:al)? (?:information|reporting|analysis|results)\b"),
        (
            "auditor's report",
            r"\b(?:independent auditors?'?s? report|report of the independent auditors?)\b",
        ),
    )
)


def exclusion_reason(header_lines: Sequence[str], section_path: Sequence[str]) -> str | None:
    """Why a page can never be a statement candidate, or None."""
    for line in header_lines:
        norm = normalise(line)
        for reason, pattern in _PATTERNS:
            if pattern.search(norm):
                return f'{reason}: header "{line}"'
    for section in section_path:
        norm = normalise(section)
        for reason, pattern in _PATTERNS:
            if pattern.search(norm):
                return f'{reason}: bookmark section "{section}"'
    return None
