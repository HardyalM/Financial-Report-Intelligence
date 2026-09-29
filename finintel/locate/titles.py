"""Primary-statement titles (EXTRACTION section 1.1).

A title matches only as a *whole line*: an optional scope qualifier, the statement noun, then only
"continued" or a period phrase. That is what keeps "Balance sheet analysis", "Income statement -
underlying basis", "Reconciliation of Group funding to the balance sheet" and "Effect on
consolidated balance sheet" out, without a list of every trap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from finintel.locate.models import Scope, StatementType
from finintel.locate.signals import normalise

# Longest nouns first so the combined statement wins over its parts.
_NOUNS: tuple[tuple[str, StatementType, bool], ...] = (
    (
        "statement of profit or loss and other comprehensive income",
        StatementType.INCOME_STATEMENT,
        True,
    ),
    ("statement of comprehensive income", StatementType.COMPREHENSIVE_INCOME, False),
    ("statement of profit or loss", StatementType.INCOME_STATEMENT, False),
    ("income statement", StatementType.INCOME_STATEMENT, False),
    ("profit and loss account", StatementType.INCOME_STATEMENT, False),
    ("statement of financial position", StatementType.BALANCE_SHEET, False),
    ("balance sheet", StatementType.BALANCE_SHEET, False),
    ("statement of cash flows", StatementType.CASH_FLOW, False),
    ("cash flow statement", StatementType.CASH_FLOW, False),
    ("statement of changes in taxpayers' equity", StatementType.CHANGES_IN_EQUITY, False),
    ("statement of changes in equity", StatementType.CHANGES_IN_EQUITY, False),
)
_QUALIFIER_WORD = r"(?:the\s+)?(?:consolidated|group|parent\s+company|company|parent)"
_QUALIFIER = rf"{_QUALIFIER_WORD}(?:\s+and\s+{_QUALIFIER_WORD})?"
_TITLE = re.compile(
    rf"^(?:(?P<qualifier>{_QUALIFIER})\s+)?"
    rf"(?P<noun>{'|'.join(re.escape(n) for n, _, _ in _NOUNS)})s?"
    r"(?P<tail>.*)$"
)
_DASH = r"[\s,:\-\u2013\u2014]*"
_TAIL = re.compile(
    rf"^(?P<continued>{_DASH}\(?(?:continued|cont'?d\.?)\)?)?"
    rf"(?:{_DASH}(?:for\s+the\s+\S.*|(?:as\s+)?at\s+\S.*|year\s+ended\s+\S.*))?"
    r"[\s*\u2020\u2021\d]{0,3}$"
)
_NOUN_TYPES = {noun: (kind, combined) for noun, kind, combined in _NOUNS}


@dataclass(frozen=True)
class TitleMatch:
    text: str  # as printed, whitespace collapsed
    statement_type: StatementType
    qualifier: str | None
    scope: Scope | None  # from the qualifier; None when the title has none
    continued: bool
    combined_with_oci: bool


def match_title(text: str) -> TitleMatch | None:
    """The statement a title-like line names, or None if the line is not a statement title."""
    norm = normalise(text)
    match = _TITLE.match(norm)
    if not match:
        return None
    tail = _TAIL.match(match.group("tail"))
    if tail is None:
        return None
    kind, combined = _NOUN_TYPES[match.group("noun")]
    qualifier = match.group("qualifier")
    return TitleMatch(
        text=" ".join(text.split()),
        statement_type=kind,
        qualifier=qualifier,
        scope=qualifier_scope(qualifier),
        continued=bool(tail.group("continued")),
        combined_with_oci=combined,
    )


def qualifier_scope(qualifier: str | None) -> Scope | None:
    if not qualifier:
        return None
    group = re.search(r"\b(?:consolidated|group)\b", qualifier) is not None
    company = re.search(r"\b(?:company|parent)\b", qualifier) is not None
    if group and company:
        return Scope.MIXED
    return Scope.COMPANY if company else Scope.GROUP
