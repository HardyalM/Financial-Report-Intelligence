"""Reported metrics (SCHEMA section 11, OQ-4 = B): figures a bank states in its own narrative.

The CET1 ratio and the net interest margin cannot be computed from the statements (NIM needs
average interest-earning assets), so they are shown as the company states them, "as reported
(p. X)", and are never used in any computation: the ratio engine reads the statement pack only.

Found by deterministic patterns, never by a model. Each figure is `value_text`, a verbatim
substring of `quote`, itself a verbatim slice of the chunk; `value` is parsed from `value_text`.
A sentence about the future ("expect", "guidance", "target") or a requirement ("minimum",
"requirement") never yields a figure. A period is the one the sentence names ("at 31 December
2024", or the prior year in a "(2023: 3.11 per cent)" comparator); a sentence naming no year is
read as the report's own year only when it carries such a comparator, otherwise the period is
null. When occurrences of one metric for one period disagree, none is shown and the reason is
recorded: two figures for one thing are a question for a person, not a pick.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from finintel.contracts.reported_metric import ReportedMetric
from finintel.narrative.models import Chunk

_VALUE = r"(?P<value>\d{1,2}(?:\.\d{1,2})?) ?(?P<unit>per cent|%)"
_COMPARATOR = re.compile(
    r"\((?:31 December )?(?P<year>(?:19|20)\d{2}): "
    r"(?P<value>\d{1,2}(?:\.\d{1,2})?) ?(?P<unit>per cent|%)(?P<qualifier> [a-z ]{1,20})?\)"
)
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "cet1",
        re.compile(
            r"(?P<label>CET1 (?:capital )?ratio)(?: at 31 December (?P<year>(?:19|20)\d{2}))?"
            r"(?: was|:| of) ?" + _VALUE,
            re.IGNORECASE,
        ),
    ),
    (
        "net_interest_margin",
        re.compile(
            r"(?P<label>(?:banking )?net interest margin)(?: for the year)?(?: was|:| of) ?"
            + _VALUE,
            re.IGNORECASE,
        ),
    ),
)
#: Sentences that state a target, an expectation or a requirement, not the reported figure.
NOT_A_FIGURE = re.compile(
    r"\b(expect\w*|guidance|target\w*|outlook|forecast\w*|will be|aim\w*|minimum|requirement|"
    r"threshold|fall below|quarter)\b",
    re.IGNORECASE,
)
LABELS = {
    "cet1_ratio": "CET1 ratio",
    "cet1_ratio_pro_forma": "CET1 ratio (pro forma)",
    "net_interest_margin": "Net interest margin",
}


@dataclass(frozen=True)
class Found:
    metrics: list[ReportedMetric]
    notes: list[str]  # why a metric was not shown (disagreeing figures)


_SENTENCE_END = re.compile(r"[.!?](?=\s)|\n\s*\n|•")


def _sentence(text: str, start: int, end: int) -> tuple[int, int]:
    """The sentence (or bullet) around [start, end): bounded by a full stop followed by space, a
    paragraph break or a bullet, whitespace trimmed. A decimal point never ends a sentence."""
    left = 0
    for m in _SENTENCE_END.finditer(text, 0, start):
        left = m.end()
    stop = _SENTENCE_END.search(text, end)
    right = len(text) if stop is None else stop.start() + (1 if stop.group(0) in ".!?" else 0)
    while left < start and text[left].isspace():
        left += 1
    while right > end and text[right - 1].isspace():
        right -= 1
    return left, right


def _context(text: str, sentence_start: int, match_start: int, match_end: int) -> str:
    """The words that decide whether a figure is the reported one: up to 80 characters before
    the metric (within the sentence) and the clause after it, up to the next comma or stop."""
    before = text[max(sentence_start, match_start - 80) : match_start]
    rest = text[match_end:]
    stop = min((i for i in (rest.find(","), rest.find(". "), rest.find(";")) if i >= 0), default=60)
    return before + " " + rest[: min(stop, 60)]


def _period(year: str | None, periods: Sequence[Mapping[str, Any]], comparator: bool) -> str | None:
    if year:
        return next(
            (str(p["id"]) for p in periods if str(p.get("end_date") or "").startswith(year)), None
        )
    return str(periods[0]["id"]) if comparator and periods else None


def find_reported_metrics(
    chunks: Sequence[Chunk],
    periods: Sequence[Mapping[str, Any]],
    page_labels: Mapping[int, str] | None = None,
) -> Found:
    """Every CET1 ratio and net interest margin the narrative states, verified and deduplicated."""
    labels = page_labels or {}
    seen: dict[tuple[str, str | None], list[ReportedMetric]] = {}
    for chunk in sorted(chunks, key=lambda c: c.char_start):
        if chunk.is_table:
            continue
        text = chunk.text
        for family, pattern in PATTERNS:
            for m in pattern.finditer(text):
                s, e = _sentence(text, m.start(), m.end())
                quote = text[s:e]
                if NOT_A_FIGURE.search(_context(text, s, m.start(), m.end())):
                    continue
                pro_forma = "pro forma" in quote.lower()
                if family == "cet1":
                    metric_id = "cet1_ratio_pro_forma" if pro_forma else "cet1_ratio"
                else:
                    metric_id = "net_interest_margin"
                after = text[m.end() : e]
                comparator = _COMPARATOR.match(after.lstrip())
                current = _period(m.groupdict().get("year"), periods, comparator is not None)
                found = [(m.start("value"), m.end("unit"), current)]
                if comparator is not None:
                    offset = m.end() + (len(after) - len(after.lstrip()))
                    vs, ve = offset + comparator.start("value"), offset + comparator.end("unit")
                    prior = _period(comparator.group("year"), periods, False)
                    found.append((vs, ve, prior))
                for vs, ve, period in found:
                    value_text = text[vs:ve]
                    number = re.match(r"\d{1,2}(?:\.\d{1,2})?", value_text)
                    if number is None or value_text not in quote:
                        continue
                    metric = ReportedMetric(
                        id=metric_id,
                        label=LABELS[metric_id],
                        label_found=m.group("label"),
                        value_text=value_text,
                        value=float(number.group(0)),
                        unit="percent",
                        period_id=period,
                        page=chunk.page_at(vs),
                        page_label=labels.get(chunk.page_at(vs)),
                        quote=quote,
                        chunk_id=chunk.chunk_id,
                        char_start=s,
                        char_end=e,
                        basis="pro forma" if pro_forma else None,
                    )
                    seen.setdefault((metric_id, period), []).append(metric)
    # A figure stated without a period only corroborates: it is folded into the report's own
    # year when that year has the metric, so a disagreement still blocks it; otherwise dropped.
    current = str(periods[0]["id"]) if periods else None
    for metric_id in {k for k, period in seen if period is None}:
        loose = seen.pop((metric_id, None))
        if (metric_id, current) in seen:
            seen[(metric_id, current)].extend(loose)
    metrics, notes = [], []
    for (metric_id, period), found_all in seen.items():
        values = sorted({f.value for f in found_all})
        if len(values) > 1:
            pages = sorted({f.page for f in found_all})
            notes.append(
                f"{LABELS[metric_id]} {period}: the report states {values} on pages {pages}; "
                "not shown until a person decides"
            )
            continue
        # Cite an occurrence that states the period itself; corroborating ones only agree.
        dated = [f for f in found_all if f.period_id == period] or found_all
        metrics.append(min(dated, key=lambda f: (f.page, f.char_start)))
    metrics.sort(key=lambda f: (f.id, f.period_id or ""))
    return Found(metrics, notes)
