"""M4.1 gate behaviour on synthetic reports: structure, pages, notes, tables, ids, limits."""

from __future__ import annotations

from pathlib import Path

import pytest

from finintel.narrative import CHUNKER_VERSION, build_chunks
from finintel.narrative.chunker import estimate_tokens
from finintel.parse.text_layer import read_text_layer
from tests.narrative.builders import (
    FILLER,
    SHA,
    build,
    by_text,
    chunk,
    excluded_map,
    make_pdf,
    sentences,
)

CHAIR = [("h", "Chair's statement"), ("p", "We delivered a steady year. " + sentences("CHAIR", 6))]
# Distinct headings: one repeated on a quarter of the pages is a running title (furniture).
FOUR = [
    [("h", f"{name} review"), ("p", sentences(f"S{n}", 5))]
    for n, name in enumerate(("Alpha", "Beta", "Gamma", "Delta"), 1)
]


def test_running_headers_folios_and_footers_are_not_content(tmp_path: Path) -> None:
    chunks = build(tmp_path, FOUR)
    text = " ".join(c.text for c in chunks)
    assert "ANNUAL REPORT" not in text and not any(
        str(n + 40) == w for c in chunks for w in c.text.split() for n in range(1, 5)
    )
    assert "S1-0" in text and "S4-4" in text


def test_a_heading_starts_a_new_chunk_and_heads_the_path(tmp_path: Path) -> None:
    page = [
        ("h", "Principal risks"),
        ("p", sentences("RISK", 4)),
        ("h2", "Supply chain"),
        ("p", sentences("SUPPLY", 4)),
    ]
    chunks = build(tmp_path, [page, *FOUR])
    risk, supply = by_text(chunks, "RISK-0"), by_text(chunks, "SUPPLY-0")
    assert risk is not supply
    assert risk.heading_path[-1] == "Principal risks" and supply.heading_path[-2:] == (
        "Principal risks",
        "Supply chain",
    )
    assert "SUPPLY" not in risk.text and "RISK" not in supply.text
    assert risk.section_id == supply.section_id == "principal_risks"


def test_a_chunk_never_crosses_a_heading_but_crosses_a_page_with_its_pages_mapped(
    tmp_path: Path,
) -> None:
    p1 = [("h", "Strategy"), ("p", sentences("FIRST", 4))]
    p2 = [("p", sentences("SECOND", 4))]  # the same section continues on the next page
    chunks = build(tmp_path, [p1, p2, *FOUR])
    c = by_text(chunks, "FIRST-0")
    assert c is by_text(chunks, "SECOND-0")  # one chunk holds both pages
    assert (c.page_start, c.page_end) == (1, 2) and [p for _, p in c.char_page_map] == [1, 2]
    assert c.page_at(c.text.index("FIRST-2")) == 1
    assert c.page_at(c.text.index("SECOND-2")) == 2  # the quote's page, not the chunk's first page
    assert c.page_at(0) == 1 and c.page_at(len(c.text) - 1) == 2
    assert {box.page for box in c.line_boxes} == {1, 2}
    with pytest.raises(IndexError):
        c.page_at(len(c.text) + 5)


NOTES = [
    (1, "Notes to the financial statements", 2),
    (2, "12. Borrowings", 2),
    (2, "13. Leases", 5),
]


def test_a_note_number_carries_across_a_page_break_until_the_next_note(tmp_path: Path) -> None:
    pages = [
        [("h", "Cover")],
        [("h", "12. Borrowings"), ("p", sentences("BORROW", 4))],
        [("p", sentences("MOREBORROW", 4))],  # no heading repeated: still note 12
        [("p", sentences("STILL12", 3))],
        [("h", "13. Leases"), ("p", sentences("LEASE", 4))],
        [("p", sentences("MORELEASE", 3))],
    ]
    chunks = build(tmp_path, pages, NOTES)
    assert by_text(chunks, "BORROW-0").note_number == "12"
    assert (
        by_text(chunks, "BORROW-0").note_title == "Borrowings"
        and by_text(chunks, "BORROW-0").is_note
    )
    carried = by_text(chunks, "STILL12-0")
    assert carried.note_number == "12" and carried.page_end == 4  # one note, three pages
    assert carried.page_at(carried.text.index("STILL12-0")) == 4
    assert (
        by_text(chunks, "LEASE-0").note_number == "13"
        and by_text(chunks, "MORELEASE-0").note_number == "13"
    )


def test_continued_note_titles_keep_the_number_and_do_not_pile_up(tmp_path: Path) -> None:
    pages = [
        [("h", "Cover")],
        [("h", "Note 12: Borrowings"), ("p", sentences("A", 3))],
        [("h", "Note 12: Borrowings continued"), ("p", sentences("B", 3))],
    ]
    chunks = build(
        tmp_path,
        pages,
        [(1, "Notes to the financial statements", 2), (2, "Note 12: Borrowings", 2)],
    )
    b = by_text(chunks, "B-0")
    assert b.note_number == "12" and b.note_title == "Borrowings"
    assert len([h for h in b.heading_path if "Borrowings" in h]) == 1


def test_chunk_ids_are_stable_and_change_with_the_chunker_version_or_document(
    tmp_path: Path,
) -> None:
    pdf = make_pdf(tmp_path / "r.pdf", FOUR)
    layer = read_text_layer(pdf)
    a = build_chunks(layer, document_sha256=SHA)
    assert [c.chunk_id for c in a] == [c.chunk_id for c in build_chunks(layer, document_sha256=SHA)]
    assert {c.chunker_version for c in a} == {CHUNKER_VERSION}
    other_version = build_chunks(layer, document_sha256=SHA, chunker_version="9.9.9")
    other_document = build_chunks(layer, document_sha256="cd" * 32)
    assert [c.text for c in a] == [c.text for c in other_version]
    assert not {c.chunk_id for c in a} & {c.chunk_id for c in other_version}
    assert not {c.chunk_id for c in a} & {c.chunk_id for c in other_document}
    assert len({c.chunk_id for c in a}) == len(a) and all(len(c.chunk_id) == 16 for c in a)


def test_offsets_index_the_narrative_text(tmp_path: Path) -> None:
    chunks = build(tmp_path, FOUR)
    narrative = "\n\n".join(c.text for c in chunks)
    for c in chunks:
        assert narrative[c.char_start : c.char_end] == c.text
    assert chunks[0].char_start == 0


# ------------------------------------------------------------------------------ tables (T18)

KPI = [
    ("Revenue", "13,907", "12,345", "+12.7%"),
    ("Operating profit", "2,100", "1,950", "+7.7%"),
    ("Free cash flow", "1,234", "1,118", "+10.4%"),
    ("Net debt", "(456)", "(512)", "-10.9%"),
]


def test_a_kpi_table_is_atomic_and_never_leaks_into_prose(tmp_path: Path) -> None:
    page = [
        ("h", "Financial review"),
        ("p", sentences("BEFORE", 4)),
        ("table", KPI),
        ("p", sentences("AFTER", 4)),
    ]
    chunks = build(tmp_path, [page, *FOUR])
    tables = [c for c in chunks if c.is_table]
    assert len(tables) == 1 and "13,907" in tables[0].text and "Net debt" in tables[0].text
    prose = [c for c in chunks if not c.is_table]
    for figure in ("13,907", "12,345", "2,100", "1,234", "+12.7%", "(456)"):
        assert not any(figure in c.text for c in prose), figure
    assert by_text(chunks, "BEFORE-0") is not by_text(
        chunks, "AFTER-0"
    )  # a table ends a prose chunk


def test_prose_with_a_few_numbers_is_not_mistaken_for_a_table(tmp_path: Path) -> None:
    text = (
        "Revenue grew 12.7% to 13,907 million and operating profit rose 7.7% to 2,100 million. "
        + sentences("NUM", 4)
    )
    chunks = build(tmp_path, [[("h", "Strategy"), ("p", text)], *FOUR])
    assert not any(c.is_table for c in chunks) and "13,907" in by_text(chunks, "NUM-0").text


def test_external_table_regions_are_excluded_from_prose(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "r.pdf", [[("h", "Strategy"), ("p", sentences("BOXED", 5))], *FOUR])
    everything = {1: [(0.0, 0.0, 595.0, 842.0)]}  # a ruled region covering the page, mostly words
    assert any(
        "BOXED" in c.text for c in chunk(pdf, table_regions=everything)
    )  # prose-only box: not a table
    numeric = make_pdf(tmp_path / "n.pdf", [[("h", "KPIs"), ("table", KPI * 2)], *FOUR])
    tables = [
        c for c in chunk(numeric, table_regions={1: [(0.0, 60.0, 595.0, 260.0)]}) if c.is_table
    ]
    assert len(tables) == 1  # the density detector and the external box agree and merge


# ------------------------------------------------------------------------------ size and structure


def test_a_long_paragraph_is_split_at_sentences_within_the_hard_maximum(tmp_path: Path) -> None:
    body = " ".join(FILLER + f"Point {n} is recorded." for n in range(80))
    one_paragraph = body[:4300]  # about 800 tokens in a single printed paragraph
    chunks = build(
        tmp_path, [[("h", "Strategy"), ("p", one_paragraph)], [("p", body[4300:5600])], *FOUR]
    )
    long_chunks = [c for c in chunks if "Point" in c.text]
    assert len(long_chunks) >= 2
    assert all(c.token_count <= 600 for c in chunks)
    for c in long_chunks[:-1]:
        assert c.text.rstrip().endswith(".")


def test_chunks_are_packed_towards_the_token_target(tmp_path: Path) -> None:
    paragraphs = [("p", sentences(f"P{n}", 4)) for n in range(14)]
    chunks = build(
        tmp_path, [[("h", "Strategy"), *paragraphs[:5]], paragraphs[5:10], paragraphs[10:], *FOUR]
    )
    strategy = [
        c
        for c in chunks
        if "P0-0" in c.text or "P13-3" in c.text or c.heading_path[-1] == "Strategy"
    ]
    assert all(c.token_count <= 600 for c in strategy)
    assert any(300 <= c.token_count <= 450 for c in strategy)
    assert len(strategy) < 14  # paragraphs are combined, not one chunk each


def test_small_sibling_sections_merge_under_their_parent(tmp_path: Path) -> None:
    page = [
        ("h", "Governance"),
        ("h2", "Board size"), ("p", "The board has nine members. " + sentences("ALPHA", 1)),
        ("h2", "Board tenure"), ("p", "Average tenure is four years. " + sentences("BETA", 1)),
    ]  # fmt: skip
    chunks = build(tmp_path, [page, *FOUR])
    merged = by_text(chunks, "ALPHA-0")
    assert merged is by_text(chunks, "BETA-0")
    assert merged.heading_path[-1] == "Governance" and merged.sub_headings == (
        "Board size",
        "Board tenure",
    )


def test_a_footnote_is_its_own_small_chunk(tmp_path: Path) -> None:
    page = [
        ("h", "Strategy"),
        ("p", sentences("BODY", 4)),
        ("foot", "1 Calculated as dividend per share over earnings per share."),
    ]
    chunks = build(tmp_path, [page, *FOUR])
    [note] = [c for c in chunks if c.is_footnote]
    assert (
        note.footnote_marker == "1" and note.token_count < 30 and "dividend per share" in note.text
    )
    assert "dividend per share" not in by_text(chunks, "BODY-0").text


def test_fragments_too_short_to_quote_are_dropped(tmp_path: Path) -> None:
    page = [("h", "Strategy"), ("p", "Net zero"), ("h2", "Plan"), ("p", sentences("REAL", 3))]
    chunks = build(tmp_path, [page, *FOUR])
    assert not any(c.text == "Net zero" for c in chunks) and by_text(chunks, "REAL-0")


# ------------------------------------------------------------------------------ exclusions


def test_excluded_sections_produce_no_chunks(tmp_path: Path) -> None:
    pages = [
        [("h", "Directors' remuneration report"), ("p", sentences("PAY", 4))],
        [("h", "Glossary"), ("p", sentences("TERMS", 4))],
        [("h", "Principal risks"), ("p", sentences("KEEP", 4))],
        [("h", "Shareholder information"), ("p", sentences("AGM", 4))],
    ]
    chunks = build(tmp_path, pages)
    texts = " ".join(c.text for c in chunks)
    assert "KEEP-0" in texts and not any(t in texts for t in ("PAY-0", "TERMS-0", "AGM-0"))


def test_excluded_pages_are_skipped_whatever_their_text_says(tmp_path: Path) -> None:
    pages = [
        [("h", "Strategy"), ("p", sentences("OK", 4))],
        [("h", "Strategy"), ("p", sentences("STATEMENT", 4))],
        *FOUR,
    ]
    chunks = build(tmp_path, pages, excluded_pages=excluded_map(p2="primary_statements"))
    assert by_text(chunks, "OK-0") and not any("STATEMENT-0" in c.text for c in chunks)


def test_company_only_accounts_under_their_own_bookmark_root_are_excluded(tmp_path: Path) -> None:
    pages = [
        [("h", "Cover")],
        [("h", "Strategy"), ("p", sentences("GROUP", 4))],
        [("h", "Balance sheet")],
        [("h", "1. Turnover"), ("p", sentences("PARENT", 4))],
    ]
    outline = [
        (1, "Group review", 2),
        (1, "Parent PLC Accounts", 3),
        (2, "Balance sheet", 3),
        (2, "1. Turnover", 4),
    ]
    chunks = build(tmp_path, pages, outline, excluded_pages=excluded_map(p3="company_statements"))
    assert by_text(chunks, "GROUP-0") and not any("PARENT-0" in c.text for c in chunks)


def test_front_matter_before_the_first_bookmark_is_excluded_only_when_there_is_an_outline(
    tmp_path: Path,
) -> None:
    pages = [
        [("h", "Cover"), ("p", sentences("COVER", 4))],
        [("h", "Strategy"), ("p", sentences("BODY", 4))],
        *FOUR,
    ]
    with_outline = build(tmp_path, pages, [(1, "Strategic report", 2)])
    assert not any("COVER-0" in c.text for c in with_outline) and by_text(with_outline, "BODY-0")
    no_outline = build(tmp_path, pages)
    assert by_text(no_outline, "COVER-0")  # without bookmarks there is no way to tell: keep it


def test_bookmarks_give_the_heading_path_and_section(tmp_path: Path) -> None:
    pages = [[("h", "Cover")], [("p", sentences("RISKS", 9))], [("p", sentences("VIAB", 9))]]
    outline = [(1, "Strategic report", 2), (2, "Principal risks", 2), (2, "Viability statement", 3)]
    chunks = build(tmp_path, pages, outline)
    assert by_text(chunks, "RISKS-0").heading_path == ("Strategic report", "Principal risks")
    assert by_text(chunks, "VIAB-0").section_id == "viability_statement"


def test_estimate_tokens_is_monotonic_and_positive() -> None:
    assert (
        estimate_tokens("") == 1
        and estimate_tokens("a b c") == 4
        and estimate_tokens("word " * 100) == 130
    )
