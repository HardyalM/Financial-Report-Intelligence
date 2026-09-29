"""Page score for one statement type: the weighted signals of EXTRACTION section 1.1.

    title 0.40, bookmark or contents 0.20, numeric density 0.20,
    column header 0.10, row vocabulary 0.10

A page is selectable at 0.55. The weights and thresholds are EXTRACTION's initial values; any change
goes into that document first, with the evidence.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from finintel.locate.models import Signal, StatementType
from finintel.locate.outline import LocationHint
from finintel.locate.signals import PageView
from finintel.locate.titles import TitleMatch

WEIGHTS = {
    "title": 0.40,
    "bookmark_or_contents": 0.20,
    "numeric_density": 0.20,
    "column_header": 0.10,
    "row_vocabulary": 0.10,
}
SELECT_THRESHOLD = 0.55
TIE_MARGIN = 0.05
NUMERIC_SHARE = 0.30
NUMERIC_ROWS = 8
VOCABULARY_MIN = 2

_VOCABULARY: dict[StatementType, tuple[str, ...]] = {
    StatementType.INCOME_STATEMENT: (
        "revenue", "turnover", "cost of sales", "gross profit", "operating profit",
        "operating loss", "finance costs", "finance income", "net finance", "profit before tax",
        "loss before tax", "taxation", "income tax", "profit for the year", "loss for the year",
        "net profit", "net interest income", "net fee and commission income", "total income",
        "operating expenses", "impairment", "operating income",
    ),
    StatementType.BALANCE_SHEET: (
        "non-current assets", "current assets", "current liabilities", "non-current liabilities",
        "net assets", "total equity", "total assets", "total liabilities", "share capital",
        "retained earnings", "loans and advances", "deposits", "cash and cash equivalents",
        "property, plant and equipment", "taxpayers' equity",
    ),
    StatementType.COMPREHENSIVE_INCOME: (
        "other comprehensive income", "total comprehensive income", "profit for the year",
        "items that will not be reclassified", "items that may be reclassified",
    ),
    StatementType.CASH_FLOW: (
        "operating activities", "investing activities", "financing activities",
        "cash and cash equivalents", "net cash",
    ),
    StatementType.CHANGES_IN_EQUITY: (
        "share capital", "retained earnings", "total equity", "dividends",
        "total comprehensive income", "balance at",
    ),
}  # fmt: skip
_VOCAB_RE = {
    kind: tuple((phrase, re.compile(rf"^(?:total\s+)?{re.escape(phrase)}\b")) for phrase in phrases)
    for kind, phrases in _VOCABULARY.items()
}


def score_page(
    view: PageView,
    statement_type: StatementType,
    title: TitleMatch | None,
    hints: Sequence[LocationHint],
) -> tuple[float, tuple[Signal, ...]]:
    years = view.header_years
    units = view.header_unit_tokens
    vocabulary = _vocabulary_hits(view, statement_type)
    signals = (
        Signal(
            name="title",
            weight=WEIGHTS["title"],
            hit=title is not None,
            detail=f'"{title.text}"' if title else "no statement title in the title region",
        ),
        Signal(
            name="bookmark_or_contents",
            weight=WEIGHTS["bookmark_or_contents"],
            hit=bool(hints),
            detail="; ".join(h.source for h in hints) or "no bookmark or contents entry",
        ),
        Signal(
            name="numeric_density",
            weight=WEIGHTS["numeric_density"],
            hit=view.numeric_share >= NUMERIC_SHARE and view.numeric_rows >= NUMERIC_ROWS,
            detail=f"numeric share {view.numeric_share:.2f} (needs {NUMERIC_SHARE:.2f}), "
            f"{view.numeric_rows} numeric rows (needs {NUMERIC_ROWS})",
        ),
        Signal(
            name="column_header",
            weight=WEIGHTS["column_header"],
            hit=len(years) >= 2 and bool(units),
            detail=f"years {list(years)}, units {list(units)}",
        ),
        Signal(
            name="row_vocabulary",
            weight=WEIGHTS["row_vocabulary"],
            hit=len(vocabulary) >= VOCABULARY_MIN,
            detail=f"{len(vocabulary)} phrases: {vocabulary[:6]}",
        ),
    )
    score = round(sum(s.weight for s in signals if s.hit), 2)
    return score, signals


def _vocabulary_hits(view: PageView, statement_type: StatementType) -> list[str]:
    found: list[str] = []
    patterns = _VOCAB_RE[statement_type]
    for line in view.lines:
        for phrase, pattern in patterns:
            if phrase not in found and pattern.match(line.norm):
                found.append(phrase)
    return found
