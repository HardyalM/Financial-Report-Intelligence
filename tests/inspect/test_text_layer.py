"""Text layer: verbatim characters, 1-based pages, fonts, lines, rules, outline, labels."""

from __future__ import annotations

from pathlib import Path

import pytest

from finintel.parse import text_layer
from finintel.parse.text_layer import PageText, TextLayer, read_text_layer
from tests.inspect.synthetic import encrypted_pdf


@pytest.fixture
def layer(mini_pdf: Path) -> TextLayer:
    return read_text_layer(mini_pdf)


def _word(page: PageText, text: str) -> text_layer.Word:
    matches = [w for w in page.words if w.text == text]
    assert matches, f"{text!r} not on page {page.page}"
    return matches[0]


def test_pages_are_one_based_pdf_indices_with_printed_labels(layer: TextLayer) -> None:
    assert layer.page_count == 7
    assert [p.page for p in layer.pages] == [1, 2, 3, 4, 5, 6, 7]
    assert layer.has_page_labels
    assert [layer.page(n).label for n in (1, 2, 3, 7)] == ["i", "ii", "140", "144"]
    for bad in (0, 8):
        with pytest.raises(IndexError):
            layer.page(bad)


def test_outline_targets_are_pdf_page_indices(layer: TextLayer) -> None:
    by_title = {e.title: (e.level, e.page) for e in layer.outline}
    assert by_title["Consolidated income statement"] == (2, 3)
    assert by_title["Consolidated balance sheet"] == (2, 4)
    assert by_title["Company balance sheet"] == (2, 5)


def test_printed_figures_are_kept_verbatim(layer: TextLayer) -> None:
    page = layer.page(3)
    texts = {w.text for w in page.words}
    for printed in ("13,907.5", "(10,321.2)", "(1,902.1)", "1,696.6", "\u2013"):
        assert printed in texts
    assert "10,321.2" not in texts  # brackets are not stripped
    assert "-" not in texts  # the printed en dash is not normalised to a hyphen


def test_words_carry_boxes_fonts_and_bold(layer: TextLayer) -> None:
    page = layer.page(3)
    title = _word(page, "Consolidated")
    assert title.bold and title.size == 16.0 and title.font == "Helvetica-Bold"
    revenue = _word(page, "Revenue")
    assert not revenue.bold and revenue.size == 9.0
    figure = _word(page, "13,907.5")
    x0, y0, x1, y1 = figure.bbox
    assert 0 <= x0 < x1 <= page.width and 0 <= y0 < y1 <= page.height
    assert x0 == 400.0  # inserted at x = 400 pt
    # Same printed row as its label, different PyMuPDF block: rows come from geometry later.
    assert abs((y0 + y1) / 2 - (revenue.bbox[1] + revenue.bbox[3]) / 2) < 0.5


def test_word_ids_agree_with_lines(layer: TextLayer) -> None:
    for page in layer.pages:
        lines = {(line.block, line.line): line for line in page.lines}
        for word in page.words:
            line = lines[(word.block, word.line)]
            assert word.text in line.text
            assert line.bbox[0] - 0.5 <= word.bbox[0] and word.bbox[2] <= line.bbox[2] + 0.5


def test_bold_lines_and_title_size(layer: TextLayer) -> None:
    page = layer.page(4)
    lines = {line.text.strip(): line for line in page.lines}
    assert (
        lines["Consolidated balance sheet"].bold and lines["Consolidated balance sheet"].size == 16
    )
    assert lines["Current assets"].bold
    assert not lines["Inventories"].bold


def test_horizontal_rules_are_captured(layer: TextLayer) -> None:
    rules = layer.page(4).rules
    subtotal_rules = [r for r in rules if r.x0 == 395.0 and r.x1 == 545.0]
    assert len(subtotal_rules) == 3  # three unlabelled subtotals on the balance sheet
    assert all(r.thickness == 0.5 for r in subtotal_rules)
    assert layer.page(1).rules == ()


def test_char_counts_ignore_whitespace(layer: TextLayer) -> None:
    for page in layer.pages:
        assert page.char_count == sum(len(w.text) for w in page.words)
        assert page.replacement_char_count == 0


def test_json_round_trip_is_lossless_and_deterministic(mini_pdf: Path, layer: TextLayer) -> None:
    data = layer.to_json()
    assert TextLayer.from_json(data) == layer
    assert read_text_layer(mini_pdf).to_json() == data
    assert layer.extractor.startswith("pymupdf ")


def test_unreadable_page_is_recorded_and_reading_continues(
    mini_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = text_layer._read_page

    def flaky(page: object, number: int, label: str | None) -> PageText:
        if number == 2:
            raise RuntimeError("damaged content stream")
        return real(page, number, label)  # type: ignore[arg-type]

    monkeypatch.setattr(text_layer, "_read_page", flaky)
    layer = read_text_layer(mini_pdf)
    assert layer.page(2).error == "page_unreadable: RuntimeError"
    assert layer.page(2).words == () and layer.page(2).label == "ii"
    assert layer.page(3).error is None and layer.page(3).words


def test_password_protected_pdf_is_refused(tmp_path: Path) -> None:
    pdf = encrypted_pdf(tmp_path / "locked.pdf", user_password="open-sesame")
    with pytest.raises(ValueError, match="password"):
        read_text_layer(pdf)


def test_render_page_png(mini_pdf: Path) -> None:
    png = text_layer.render_page_png(mini_pdf, 3, dpi=30)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
