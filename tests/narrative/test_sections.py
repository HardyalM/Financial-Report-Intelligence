"""Section taxonomy, note headings and the M4.1 gate's own audit."""

from __future__ import annotations

from typing import Any

import pytest

from finintel.narrative.sections import EXCLUDED, classify, is_heading_text, note_heading
from scripts import gate


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("12. Borrowings", ("12", "Borrowings")),
        ("12 Borrowings", ("12", "Borrowings")),
        ("12.1 Lease liabilities", ("12.1", "Lease liabilities")),
        ("Note 12: Borrowings", ("12", "Borrowings")),
        ("note 12 Borrowings", ("12", "Borrowings")),
        ("6C. TAX ON ITEMS RECOGNISED IN EQUITY", ("6C", "TAX ON ITEMS RECOGNISED IN EQUITY")),
        ("21. ACQUISITIONS AND DISPOSALS continued", ("21", "ACQUISITIONS AND DISPOSALS")),
        ("Note 11: Share-based payments continued", ("11", "Share-based payments")),
    ],
)
def test_note_headings(heading: str, expected: tuple[str, str]) -> None:
    assert note_heading(heading) == expected


@pytest.mark.parametrize(
    "text",
    [
        "2024 results were strong",
        "12 months ended",
        "Revenue 13,907",
        "12.",
        "Note 12:",
        "borrowings",
        "10 key facts",
    ],
)
def test_not_note_headings(text: str) -> None:
    assert note_heading(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "■Stepped up investment in a social-",
        "• Digital channels",
        "- a list item",
        "first marketing approach",
        "Revenue grew.",
    ],
)
def test_bullets_fragments_and_sentences_are_not_headings(text: str) -> None:
    assert not is_heading_text(text)


@pytest.mark.parametrize(
    "text",
    ["Principal risks", "Supply chain disruption", "12. Borrowings", "Our strategy: GAP 2030"],
)
def test_headings(text: str) -> None:
    assert is_heading_text(text)


@pytest.mark.parametrize(
    ("path", "section"),
    [
        (("Strategic report", "Principal risks"), "principal_risks"),
        (("Governance", "Audit committee report"), "audit_committee_report"),
        (("Governance", "Directors' remuneration report", "Policy"), "remuneration_report"),
        (
            ("Financial statements", "Independent auditor's report", "Key audit matters"),
            "auditors_report",
        ),
        (("Notes", "2. Accounting policies"), "notes_accounting_policies"),
        (("Strategic report", "Viability statement"), "viability_statement"),
        (("Strategic report", "Going concern"), "going_concern"),
        (("Strategic report", "Chair's statement"), "chair_statement"),
        (("Financial statements", "Consolidated balance sheet"), "primary_statements"),
        (("Shareholder information",), "shareholder_information"),
        (("Glossary",), "glossary_apm"),
        (("Something unrecognised",), "narrative_other"),
        (("Notes to the financial statements", "12. Borrowings"), "notes_other"),
    ],
)
def test_taxonomy(path: tuple[str, ...], section: str) -> None:
    assert classify(path) == section


def test_the_deepest_matching_title_decides_except_for_company_material() -> None:
    assert (
        classify(("Governance", "Remuneration report", "Audit committee report"))
        == "audit_committee_report"
    )
    assert (
        classify(("Unilever PLC accounts", "Notes to the company accounts", "Principal risks"))
        == "company_statements"
    )
    assert (
        classify(("Notes to the parent company financial statements", "Note 2: Risk management"))
        == "company_statements"
    )


def test_the_excluded_set_matches_the_policy_table() -> None:
    assert {"primary_statements", "company_statements", "remuneration_report"} <= EXCLUDED
    assert "principal_risks" not in EXCLUDED and "narrative_other" not in EXCLUDED


# ------------------------------------------------------------------------------ the gate's audit


def _chunk(
    chunk_id: str, section: str = "principal_risks", pages: tuple[int, int] = (10, 10), **extra: Any
) -> dict[str, Any]:
    return {
        "chunk_id": chunk_id, "section_id": section, "page_start": pages[0], "page_end": pages[1],
        "is_table": False, "is_footnote": False,
        "line_boxes": [{"page": pages[0], "bbox": [50.0, 100.0, 500.0, 110.0]}], **extra,
    }  # fmt: skip


def test_the_m4_1_audit_passes_clean_chunks_and_catches_each_violation() -> None:
    clean = [_chunk("a"), _chunk("b", pages=(11, 12))]
    assert all(ok for ok, _ in gate.check_m41(clean, {141: "primary_statements"}, {}))

    in_statements = [_chunk("a", section="company_statements")]
    assert [ok for ok, _ in gate.check_m41(in_statements, {}, {})] == [True, False, True, True]
    on_page = [_chunk("a", pages=(140, 142))]
    assert [ok for ok, _ in gate.check_m41(on_page, {141: "primary_statements"}, {})] == [
        True,
        True,
        False,
        True,
    ]
    no_page = [{**_chunk("a"), "page_start": 0}]
    assert not gate.check_m41(no_page, {}, {})[0][0]

    table = {10: [(40.0, 95.0, 520.0, 130.0)]}  # an independent table region around the prose line
    assert [ok for ok, _ in gate.check_m41([_chunk("a")], {}, table)] == [True, True, True, False]
    assert all(
        ok for ok, _ in gate.check_m41([_chunk("a", is_table=True)], {}, table)
    )  # tables may sit there
    far = {10: [(40.0, 300.0, 520.0, 400.0)]}
    assert all(ok for ok, _ in gate.check_m41([_chunk("a")], {}, far))


def test_a_key_audit_matter_about_the_parent_stays_in_the_auditors_report() -> None:
    kam = (
        "KPMG Independent Auditor's Report",
        "4. Key Audit matters",
        "4.3 Investments and subsidiaries (Parent company)",
    )
    assert classify(kam) == "auditors_report"
    # the parent's own accounts are still excluded, inside or outside an audit report
    assert classify(("Parent company balance sheet",)) == "company_statements"
    assert classify(("Financial statements", "Parent company information")) == "company_statements"
    assert classify(("Company accounts", "Notes")) == "company_statements"
