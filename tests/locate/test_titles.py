"""Statement titles match as whole lines only. Negatives are real lines from the two goldens."""

from __future__ import annotations

import pytest

from finintel.locate.models import Scope, StatementType
from finintel.locate.titles import match_title

IS, SOCI, BS = (
    StatementType.INCOME_STATEMENT,
    StatementType.COMPREHENSIVE_INCOME,
    StatementType.BALANCE_SHEET,
)
CF, SOCE = StatementType.CASH_FLOW, StatementType.CHANGES_IN_EQUITY


@pytest.mark.parametrize(
    ("text", "kind", "scope"),
    [
        ("Consolidated income statement", IS, Scope.GROUP),
        ("Group income statement", IS, Scope.GROUP),
        ("CONSOLIDATED INCOME STATEMENT", IS, Scope.GROUP),
        ("Consolidated statement of profit or loss", IS, Scope.GROUP),
        ("Profit and loss account", IS, None),
        ("Consolidated statement of comprehensive income", SOCI, Scope.GROUP),
        ("Statement of comprehensive income", SOCI, None),
        ("Consolidated balance sheet", BS, Scope.GROUP),
        ("Consolidated statement of financial position", BS, Scope.GROUP),
        ("Statement of financial position", BS, None),
        ("Balance sheet", BS, None),
        ("Company balance sheet", BS, Scope.COMPANY),
        ("Parent company balance sheet", BS, Scope.COMPANY),
        ("The Group balance sheet", BS, Scope.GROUP),
        ("Group and company balance sheets", BS, Scope.MIXED),
        ("Consolidated cash flow statement", CF, Scope.GROUP),
        ("Consolidated statement of cash flows", CF, Scope.GROUP),
        ("Consolidated statement of changes in equity", SOCE, Scope.GROUP),
        ("Statement of changes in taxpayers\u2019 equity", SOCE, None),
    ],
)
def test_statement_titles(text: str, kind: StatementType, scope: Scope | None) -> None:
    match = match_title(text)
    assert match is not None
    assert match.statement_type is kind and match.scope is scope
    assert not match.continued


@pytest.mark.parametrize(
    "text",
    [
        "Consolidated income statement for the year ended 31 December 2024",
        "Consolidated balance sheet at 31 December 2024",
        "Consolidated balance sheet as at 29 March 2025",
        "Consolidated income statement\u00b9",  # superscript footnote marker
        "Consolidated   income\nstatement",  # wrapped or spaced
    ],
)
def test_period_phrases_and_markers_are_allowed(text: str) -> None:
    assert match_title(text) is not None


@pytest.mark.parametrize(
    "text",
    ["Consolidated balance sheet (continued)", "Consolidated balance sheet continued",
     "Consolidated balance sheet \u2013 continued", "Consolidated balance sheet cont'd"],
)  # fmt: skip
def test_continued_titles(text: str) -> None:
    match = match_title(text)
    assert match is not None and match.statement_type is BS and match.continued


def test_combined_statement_is_an_income_statement() -> None:
    match = match_title("Consolidated statement of profit or loss and other comprehensive income")
    assert match is not None and match.statement_type is IS and match.combined_with_oci


@pytest.mark.parametrize(
    "text",
    [
        # Lloyds Banking Group 2024
        "Balance sheet analysis",
        "Income statement \u2013 underlying basisA",
        "Reconciliation of Group funding to the balance sheet (audited)",
        "Key balance sheet metrics",
        "On balance sheet encumbered and unencumbered assets",
        "Charge to the income statement",
        "Liabilities held at fair value through profit or loss",
        "Note 43: Events since the balance sheet date",
        # Unilever 2024
        "EFFECT ON CONSOLIDATED BALANCE SHEET",
        "26. Events after the balance sheet date",
        "6C. TAX ON ITEMS RECOGNISED IN EQUITY OR OTHER COMPREHENSIVE INCOME",
        "Consolidated Financial Statements",
        "NOTES TO THE CONSOLIDATED FINANCIAL STATEMENTS UNILEVER GROUP",
        # APM and summary pages
        "Adjusted income statement",
        "Summary consolidated income statement",
        "Five-year summary: consolidated income statement",
        "Consolidated income statement 2021-2025",
    ],
)
def test_traps_are_not_titles(text: str) -> None:
    assert match_title(text) is None
