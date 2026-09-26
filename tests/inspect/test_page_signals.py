"""Inspection signals: counts a human can rank pages by. Not the M2.1 locator."""

from __future__ import annotations

from pathlib import Path

import pytest

from finintel.cli import page_signals as ps
from finintel.parse.text_layer import Line, PageText, TextLayer, Word, read_text_layer


@pytest.fixture
def layer(mini_pdf: Path) -> TextLayer:
    return read_text_layer(mini_pdf)


@pytest.mark.parametrize(
    "token",
    ["13,907.5", "(1,234)", "(10,321.2)", "-12", "\u221212.5", "\u2013", "-", "£13.9", "12.4*",
     "2025", "0", "1,000,000"],
)  # fmt: skip
def test_numeric_tokens(token: str) -> None:
    assert ps._NUMERIC.match(token)


@pytest.mark.parametrize("token", ["n/a", "12a", "1,23", "note", "(", "12,34,567", "£"])
def test_non_numeric_tokens(token: str) -> None:
    assert not ps._NUMERIC.match(token)


@pytest.mark.parametrize(
    ("text", "unit"),
    [("£m", "£m"), ("£ m", "£ m"), ("£'000", "£'000"), ("£\u2019000", "£'000"),
     ("£000", "£000"), ("US$m", "us$m"), ("$m", "$m"), ("€m", "€m"),
     ("£ million", "£ million"), ("£ millions", "£ millions"), ("EURm", "eurm")],
)  # fmt: skip
def test_unit_tokens(text: str, unit: str) -> None:
    matches = [ps.normalise(m.group(0)) for m in ps._UNIT.finditer(f"2025 {text} 2024")]
    assert matches == [unit]


@pytest.mark.parametrize("text", ["£more than", "£200m revenue", "$money", "€mbargo"])
def test_prose_is_not_a_unit_token(text: str) -> None:
    assert not ps._UNIT.search(text)


def test_normalise() -> None:
    assert ps.normalise("Directors\u2019  Report\n\ufb01nance") == "directors' report finance"


def test_keywords_match_across_line_breaks() -> None:
    page = _page([_line("Group balance"), _line("sheet and the income", y=20)])
    assert ps.page_signals(page, ()).keyword_hits["balance sheet"] == 1


def test_statement_page_signals(layer: TextLayer) -> None:
    s = ps.page_signals(layer.page(4), layer.outline)
    assert s.title_lines[0] == "Consolidated balance sheet"
    assert s.title_keyword_hits == ("balance sheet",)
    assert s.outline_titles == ("Consolidated balance sheet",)
    assert s.unit_tokens == ("£m",) and s.header_years == ("2025", "2024")
    assert s.numeric_rows >= 12 and s.table_like
    assert s.label == "141" and s.has_text


def test_narrative_page_mentions_but_is_not_titled(layer: TextLayer) -> None:
    s = ps.page_signals(layer.page(2), layer.outline)
    assert s.keyword_hits["balance sheet"] >= 1 and s.keyword_hits["income statement"] == 1
    assert not s.titled_as_statement and not s.table_like
    assert s.title_lines == ("Chief Executive's review",)


def test_visual_rows_join_cells_from_different_blocks(layer: TextLayer) -> None:
    rows = [[w.text for w in row] for row in ps.visual_rows(layer.page(3).words)]
    assert ["Revenue", "3", "13,907.5", "12,345.0"] in rows


def test_ranking_puts_titled_statements_first(layer: TextLayer) -> None:
    ranked = ps.rank_pages(ps.page_signals(p, layer.outline) for p in layer.pages)
    assert {ranked[0].page, ranked[1].page} == {3, 4}
    assert ranked[2].page == 5  # the company balance sheet: titled, fewer numeric rows
    assert all(not s.titled_as_statement for s in ranked[3:])


def test_pages_without_any_statement_mention_are_not_ranked() -> None:
    quiet = ps.page_signals(_page([_line("Glossary of terms")]), ())
    assert not quiet.mentions_statement
    assert ps.rank_pages([quiet]) == []


def test_empty_page() -> None:
    s = ps.page_signals(_page([]), ())
    assert s.words == 0 and s.numeric_token_share == 0.0 and s.title_lines == ()
    assert not s.has_text


def _line(text: str, y: float = 0.0, size: float = 9.0) -> tuple[Line, list[Word]]:
    words, x = [], 50.0
    for token in text.split():
        words.append(
            Word(text=token, bbox=(x, 100 + y, x + 30, 110 + y), block=0, line=int(y), font="helv",
                 size=size, bold=False)
        )  # fmt: skip
        x += 35
    line = Line(
        block=0, line=int(y), bbox=(50, 100 + y, x, 110 + y), text=text, size=size, bold=False
    )
    return line, words


def _page(lines: list[tuple[Line, list[Word]]]) -> PageText:
    return PageText(
        page=1,
        label=None,
        width=595,
        height=842,
        rotation=0,
        lines=tuple(line for line, _ in lines),
        words=tuple(w for _, ws in lines for w in ws),
        char_count=sum(len(w.text) for _, ws in lines for w in ws),
    )
