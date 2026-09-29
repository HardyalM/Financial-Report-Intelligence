"""Scope evidence order, and the pages that are never candidates."""

from __future__ import annotations

import pytest

from finintel.locate.exclusions import exclusion_reason
from finintel.locate.models import Scope
from finintel.locate.scope import classify_scope, is_entity_label


def test_title_qualifier_wins() -> None:
    scope, evidence = classify_scope(
        Scope.GROUP, "Consolidated balance sheet", [], ["COMPANY ACCOUNTS UNILEVER PLC"], []
    )
    assert scope is Scope.GROUP and "title" in evidence


def test_entity_columns_make_a_mixed_page() -> None:
    scope, evidence = classify_scope(None, None, ["Group", "Company", "Group", "Company"], [], [])
    assert scope is Scope.MIXED and "entity columns" in evidence
    assert classify_scope(None, None, ["Group", "Trust"], [], [])[0] is Scope.MIXED


@pytest.mark.parametrize(
    ("header", "scope"),
    [
        ("COMPANY ACCOUNTS UNILEVER PLC", Scope.COMPANY),
        ("Company Accounts Unilever PLC", Scope.COMPANY),
        ("Parent company financial statements", Scope.COMPANY),
        ("CONSOLIDATED FINANCIAL STATEMENTS UNILEVER GROUP", Scope.GROUP),
        ("Unilever Group", Scope.GROUP),
    ],
)
def test_header_above_the_title(header: str, scope: Scope) -> None:
    got, evidence = classify_scope(None, "Balance sheet", [], [header], [])
    assert got is scope and header in evidence


def test_a_header_naming_both_entities_is_not_evidence() -> None:
    scope, evidence = classify_scope(
        None, None, [], ["Group and Company financial statements", "Company accounts"], []
    )
    assert scope is Scope.COMPANY and "Company accounts" in evidence


def test_bookmark_section_is_the_last_resort() -> None:
    scope, evidence = classify_scope(
        None, None, [], ["Balance sheet"], ["Financial statements", "Company accounts"]
    )
    assert scope is Scope.COMPANY and "bookmark" in evidence


def test_no_evidence_is_unknown() -> None:
    assert (
        classify_scope(None, None, [], ["Balance sheet"], ["Financial statements"])[0]
        is Scope.UNKNOWN
    )


@pytest.mark.parametrize("label", ["Group", "the group", "Company", "Parent company", "Trust"])
def test_entity_labels(label: str) -> None:
    assert is_entity_label(label)


@pytest.mark.parametrize("label", ["Group revenue", "Amounts owed by group undertakings", "2024"])
def test_row_labels_are_not_entity_labels(label: str) -> None:
    assert not is_entity_label(label)


@pytest.mark.parametrize(
    ("header", "reason"),
    [
        ("Five-year summary", "multi-year summary"),
        ("10 year record", "multi-year summary"),
        ("Financial review", "financial review"),
        ("Chief Financial Officer's review", "financial review"),
        ("Alternative performance measures", "APM reconciliation"),
        ("Independent auditor\u2019s report to the members of Example plc", "auditor's report"),
        ("Segment information", "segment note"),
        ("2024 highlights", "highlights or KPI page"),
        ("Key performance indicators", "highlights or KPI page"),
    ],
)
def test_hard_exclusions(header: str, reason: str) -> None:
    got = exclusion_reason([header], [])
    assert got is not None and got.startswith(reason)


def test_exclusion_from_the_bookmark_section() -> None:
    got = exclusion_reason([], ["Strategic report", "Financial review"])
    assert got is not None and "bookmark section" in got


@pytest.mark.parametrize(
    "header",
    [
        "Consolidated financial statements",
        "Strategic report",
        "Notes to the consolidated financial statements",
        "Governance",
        "Financial statements",
    ],
)
def test_ordinary_sections_are_not_excluded(header: str) -> None:
    assert exclusion_reason([header], ["Financial statements"]) is None
