"""Which entity a statement page describes (EXTRACTION sections 1.2 and 3).

Evidence, strongest first:
1. the title's own qualifier ("Consolidated balance sheet", "Parent company balance sheet");
2. standalone entity column labels ("Group" and "Company" side by side: mixed, M2.3 picks columns);
3. header lines printed above the title ("COMPANY ACCOUNTS UNILEVER PLC"), chrome excluded;
4. the PDF bookmark section the page sits in.

Row labels are never evidence: "Amounts owed by group undertakings" sits on company balance sheets.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from finintel.locate.models import Scope
from finintel.locate.signals import normalise

_GROUP = re.compile(r"\b(?:consolidated|group)\b")
_COMPANY = re.compile(r"\b(?:parent company|company|parent)\b")
_GROUP_LABELS = frozenset({"group", "the group", "consolidated"})
_COMPANY_LABELS = frozenset(
    {"company", "the company", "parent company", "parent", "trust", "the trust"}
)


def scope_of_text(text: str) -> Scope | None:
    norm = normalise(text)
    group, company = bool(_GROUP.search(norm)), bool(_COMPANY.search(norm))
    if group and company:
        return Scope.MIXED
    if group:
        return Scope.GROUP
    if company:
        return Scope.COMPANY
    return None


def classify_scope(
    title_scope: Scope | None,
    title_text: str | None,
    column_labels: Sequence[str],
    header_lines: Sequence[str],
    section_path: Sequence[str],
) -> tuple[Scope, str]:
    """(scope, evidence) for one candidate page."""
    if title_scope is not None:
        return title_scope, f'title "{title_text}"'

    labels = {normalise(label) for label in column_labels}
    if labels & _GROUP_LABELS and labels & _COMPANY_LABELS:
        found = sorted(labels & (_GROUP_LABELS | _COMPANY_LABELS))
        return Scope.MIXED, f"entity columns {found}"

    for line in header_lines:
        scope = scope_of_text(line)
        if scope in (Scope.GROUP, Scope.COMPANY):
            return scope, f'header "{line}"'
    for section in reversed(section_path):
        scope = scope_of_text(section)
        if scope in (Scope.GROUP, Scope.COMPANY):
            return scope, f'bookmark section "{section}"'
    return Scope.UNKNOWN, "no qualifier in title, entity columns, headers or bookmarks"


def is_entity_label(text: str) -> bool:
    norm = normalise(text)
    return norm in _GROUP_LABELS or norm in _COMPANY_LABELS
