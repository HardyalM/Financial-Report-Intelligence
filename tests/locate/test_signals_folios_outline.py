"""Page geometry (including rotation), chrome, folios, bookmarks and contents pages."""

from __future__ import annotations

from finintel.locate.folios import infer_folios
from finintel.locate.outline import bookmark_hints, contents_hints, section_paths
from finintel.locate.signals import PageView, detect_chrome
from finintel.parse.text_layer import OutlineEntry
from tests.locate.builders import Printed, layer, page


def test_title_region_follows_the_displayed_page_on_rotated_pages() -> None:
    # On a /Rotate 90 page the displayed top is the unrotated left edge.
    rotated = page(
        [
            Printed("Consolidated balance sheet", x=40, y=300, size=16, bold=True),
            *(Printed(f"Row {i} 1,000 2,000", x=300, y=100 + 20 * i) for i in range(12)),
        ],
        rotation=90,
    )
    view = PageView(rotated)
    assert (view.width, view.height) == (842.0, 595.0)
    assert [v.text for v in view.title_lines] == ["Consolidated balance sheet"]


def test_bottom_of_an_unrotated_page_is_not_the_title_region() -> None:
    footer = page([Printed("Consolidated balance sheet", x=40, y=800, size=16, bold=True)])
    assert PageView(footer).title_lines == ()


def test_numeric_rows_value_columns_and_header_years() -> None:
    table = page(
        [
            Printed("2025", x=420, y=120, bold=True),
            Printed("2024", x=500, y=120, bold=True),
            Printed("£m", x=425, y=132),
            Printed("£m", x=505, y=132),
            *(Printed(f"Line item {chr(65 + i)}", x=50, y=150 + 15 * i) for i in range(10)),
            *(Printed("1,234", x=420, y=150 + 15 * i) for i in range(10)),
            *(Printed("(567)", x=500, y=150 + 15 * i) for i in range(10)),
        ]
    )
    view = PageView(table)
    assert view.header_years == ("2025", "2024")
    assert view.header_unit_tokens == ("£m",)
    assert view.numeric_rows == 11  # ten figure rows, plus the year header (two numeric tokens)
    assert view.value_columns == 2


def test_chrome_is_lines_repeated_across_pages() -> None:
    pages = [
        page(
            [Printed("STRATEGIC REPORT", x=50, y=20), Printed(f"Section {n}", x=50, y=60, size=14)],
            number=n,
        )
        for n in range(1, 9)
    ]
    chrome = detect_chrome(layer(pages))
    assert "strategic report" in chrome
    assert not any(c.startswith("section") for c in chrome)


def test_folios_from_margin_numbers() -> None:
    pages = [
        page([Printed("Body text", x=50, y=300), Printed(str(n + 120), x=540, y=820)], number=n)
        for n in range(1, 11)
    ]
    folios = infer_folios([PageView(p) for p in pages])
    assert folios.offset == -120
    assert folios.label(3) == "123" and folios.pdf_page(125) == 5


def test_folios_ignore_years_and_need_support() -> None:
    noisy = [
        page(
            [Printed("Annual Report 2024", x=50, y=820), Printed(str(n - 3), x=540, y=820)],
            number=n,
        )
        for n in range(4, 14)
    ]
    assert infer_folios([PageView(p) for p in noisy]).offset == 3
    short = [page([Printed(str(n), x=540, y=820)], number=n) for n in range(1, 4)]
    assert infer_folios([PageView(p) for p in short]).offset is None


def test_folio_only_where_printed() -> None:
    pages = [
        page(
            [Printed(str(n - 2), x=540, y=820)] if n != 7 else [Printed("Photo", x=50, y=300)],
            number=n,
        )
        for n in range(3, 13)
    ]
    folios = infer_folios([PageView(p) for p in pages])
    assert folios.offset == 2 and folios.label(7) is None and folios.label(8) == "6"


def test_section_paths_follow_bookmark_nesting() -> None:
    outline = [
        OutlineEntry(level=1, title="Strategic report", page=2),
        OutlineEntry(level=2, title="Financial review", page=3),
        OutlineEntry(level=1, title="Financial statements", page=5),
        OutlineEntry(level=2, title="Consolidated income statement", page=5),
        OutlineEntry(level=2, title="Company balance sheet", page=8),
    ]
    paths = section_paths(outline, 9)
    assert paths[1] == ()
    assert paths[4] == ("Strategic report", "Financial review")
    assert paths[6] == ("Financial statements", "Consolidated income statement")
    assert paths[9] == ("Financial statements", "Company balance sheet")


def test_bookmark_hints_are_statement_titles_only() -> None:
    hints = bookmark_hints(
        [
            OutlineEntry(level=2, title="Balance sheet", page=143),
            OutlineEntry(level=2, title="26. Events after the balance sheet date", page=193),
            OutlineEntry(level=2, title="SOCI - Income", page=141),
        ]
    )
    assert list(hints) == [143]
    assert hints[143][0].source == 'bookmark "Balance sheet"'


def test_contents_page_maps_printed_folios_to_pdf_pages() -> None:
    contents = page(
        [
            Printed("Contents", x=50, y=60, size=18, bold=True),
            Printed("Consolidated income statement ........ 138", x=50, y=300),
            Printed("140 Consolidated balance sheet", x=50, y=320),
            Printed("Independent auditor's report 128", x=50, y=340),
        ],
        number=2,
    )
    others = [page([Printed(str(n - 3), x=540, y=820)], number=n) for n in range(3, 160)]
    doc = layer([page([], number=1), contents, *others])
    views = [PageView(p) for p in doc.pages]
    hints = contents_hints(views, infer_folios(views), doc)
    assert sorted(hints) == [141, 143]
    assert hints[141][0].match.statement_type.value == "income_statement"
