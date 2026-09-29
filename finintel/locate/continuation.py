"""Multi-page statements and two-page spreads (EXTRACTION section 2).

Page p+1 continues statement S on page p only if all of these hold:
- no new statement title in its title region (a "continued" title of S itself is allowed);
- a numeric table with the same number of value columns;
- the same header year tokens, or a "continued" marker;
- consecutive page labels, where the PDF defines them.
"""

from __future__ import annotations

import re

from finintel.locate.models import Continuation, StatementType
from finintel.locate.signals import PageView
from finintel.locate.titles import match_title

SPREAD_RATIO = 1.3
MIN_TABLE_ROWS = 4  # numeric rows a continuation page must carry
_CONTINUED = re.compile(r"\b(?:continued|cont'?d)\b")
_FOLIO = re.compile(r"^\d{1,4}$")


def continues(prev: PageView, nxt: PageView, statement_type: StatementType) -> Continuation | None:
    continued_title = False
    for line in nxt.title_lines:
        match = match_title(line.text)
        if match is None:
            continue
        if match.statement_type is statement_type and match.continued:
            continued_title = True
            continue
        return None  # a new statement starts here
    if nxt.numeric_rows < MIN_TABLE_ROWS or prev.value_columns == 0:
        return None
    if nxt.value_columns != prev.value_columns:
        return None
    marker = continued_title or any(_CONTINUED.search(v.norm) for v in nxt.band(0.25))
    same_years = bool(prev.header_years) and nxt.header_years == prev.header_years
    if not (same_years or marker):
        return None
    if not _consecutive_labels(prev, nxt):
        return None
    evidence = "; ".join(
        part
        for part in (
            "no new statement title",
            f"{nxt.value_columns} value columns as on p.{prev.page.page}",
            f"same header years {list(nxt.header_years)}" if same_years else "",
            "'continued' marker" if marker else "",
        )
        if part
    )
    return Continuation(page=nxt.page.page, value_columns=nxt.value_columns, evidence=evidence)


def is_spread(view: PageView) -> bool:
    """A landscape page carrying two folios, one in each half: two printed pages on one PDF page."""
    if view.width / view.height <= SPREAD_RATIO:
        return False
    bottom = view.height * 0.92
    halves = {
        box[0] < view.width / 2
        for word, box in view.words
        if box[1] >= bottom and _FOLIO.match(word.text)
    }
    return halves == {True, False}


def _consecutive_labels(prev: PageView, nxt: PageView) -> bool:
    a, b = prev.page.label, nxt.page.label
    if a is None or b is None or not (a.isdigit() and b.isdigit()):
        return True  # no labels, or non-numeric labels: this rule does not apply
    return int(b) == int(a) + 1
