"""Render a synthetic spec to a PDF with PyMuPDF.

The layout imitates a UK annual report closely enough to exercise the locator and, later, the
table model: a navigation bar, section headers, bold titles, a notes column, right-aligned figures,
rules above subtotals, and printed folios in the footer (no PDF page labels, like both goldens).
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from evals.synthetic.spec import (
    ColumnSpec,
    NarrativePage,
    Row,
    Spec,
    SpreadPage,
    StatementPage,
    page_columns,
)

A4 = (595.0, 842.0)
LABEL_X = 50.0
NOTE_X = 330.0
FIRST_VALUE_RIGHT = 440.0
VALUE_STEP = 80.0
ROW_STEP = 15.0
PROSE = (
    "The group delivered a resilient performance in a challenging market, supported by a strong "
    "balance sheet and disciplined capital allocation. The board remains focused on cash "
    "generation, customer service and long-term value creation for all stakeholders. "
)
# Base-14 Helvetica encodes Latin-1 only; other glyphs (dashes, the euro sign) use MuPDF's
# built-in Droid Sans Fallback, which writes a ToUnicode map as a typeset report would.
_FALLBACK = pymupdf.Font("cjk")


def render(spec: Spec, path: Path) -> Path:
    doc = pymupdf.open()
    for number, page_spec in enumerate(spec.pages, start=1):
        if isinstance(page_spec, SpreadPage):
            page = doc.new_page(width=2 * A4[0], height=A4[1])
            halves = ((0.0, page_spec.left, 2 * number - 1), (A4[0], page_spec.right, 2 * number))
            for dx, half, folio in halves:
                _chrome(page, spec, str(folio - spec.folio_offset), dx)
                _half(page, spec, half, dx)
            continue
        page = doc.new_page(width=A4[0], height=A4[1])
        _chrome(page, spec, str(number - spec.folio_offset), 0.0)
        _half(page, spec, page_spec, 0.0)
    doc.set_metadata(
        {"title": f"{spec.company} synthetic: {spec.name}", "producer": "finintel evals"}
    )
    doc.save(path)
    doc.close()
    return path


def _half(
    page: pymupdf.Page, spec: Spec, content: StatementPage | NarrativePage, dx: float
) -> None:
    if isinstance(content, StatementPage):
        _statement(page, spec, content, dx)
    else:
        _narrative(page, content, dx)


def _text(
    page: pymupdf.Page, x: float, y: float, text: str, size: float = 8, bold: bool = False
) -> None:
    if any(ord(char) > 0xFF for char in text):
        writer = pymupdf.TextWriter(page.rect)
        writer.append((x, y), text, font=_FALLBACK, fontsize=size)
        writer.write_text(page)
    else:
        page.insert_text((x, y), text, fontsize=size, fontname="hebo" if bold else "helv")


def _right(
    page: pymupdf.Page, right: float, y: float, text: str, size: float = 8, bold: bool = False
) -> None:
    font = _FALLBACK if any(ord(char) > 0xFF for char in text) else None
    width = (
        font.text_length(text, fontsize=size)
        if font is not None
        else pymupdf.get_text_length(text, fontname="hebo" if bold else "helv", fontsize=size)
    )
    _text(page, right - width, y, text, size, bold)


def _chrome(page: pymupdf.Page, spec: Spec, folio: str, dx: float) -> None:
    for i, item in enumerate(spec.chrome):
        _text(page, dx + LABEL_X + 120 * i, 22, item.upper(), size=6.5)
    footer = f"{spec.company} Annual Report and Accounts {spec.periods[0]}"
    _text(page, dx + LABEL_X, 822, footer, size=7)
    _right(page, dx + 545, 822, folio, size=7)


def _narrative(page: pymupdf.Page, spec: NarrativePage, dx: float) -> None:
    if spec.header:
        _text(page, dx + LABEL_X, 48, spec.header, size=9)
    _text(page, dx + LABEL_X, 78, spec.title, size=16, bold=True)
    box = pymupdf.Rect(dx + LABEL_X, 100, dx + 545, 600)
    page.insert_textbox(box, PROSE * spec.paragraphs, fontsize=9, fontname="helv")


def _statement(page: pymupdf.Page, spec: Spec, sheet: StatementPage, dx: float) -> None:
    if sheet.header:
        _text(page, dx + LABEL_X, 48, sheet.header, size=9)
    if sheet.title:
        _text(page, dx + LABEL_X, 78, sheet.title, size=16, bold=True)
    if sheet.subtitle:
        _text(page, dx + LABEL_X, 94, sheet.subtitle, size=8)
    columns = page_columns(spec, sheet)
    rights, note_x = _layout(len(columns), dx)
    header_rows = [
        ("entity", any(c.entity for c in columns)),
        ("period", True),
        ("sub", any(c.sub for c in columns)),
        ("unit", bool(spec.unit)),
    ]
    present = [name for name, shown in header_rows if shown]
    y_of = {name: 136.0 - 11.0 * (len(present) - 1 - i) for i, name in enumerate(present)}
    if sheet.notes_header:
        _text(page, note_x, y_of["period"], sheet.notes_header, size=7, bold=True)
    size = 7.0 if len(columns) > 3 else 8.0
    for name in present:
        _header_row(page, name, columns, rights, y_of[name], spec.unit, size)
    y = 158.0
    for row in sheet.rows:
        _row(page, row, rights, y, dx, note_x, size)
        y += ROW_STEP


def _layout(count: int, dx: float) -> tuple[list[float], float]:
    """Value-column right edges and the notes x: three columns or fewer as before; more fit
    between x = 300 and 555 (columnar and entity layouts)."""
    if count <= 3:
        return [dx + FIRST_VALUE_RIGHT + VALUE_STEP * i for i in range(count)], dx + NOTE_X
    step = 48.0
    rights = [dx + 555.0 - step * (count - 1 - i) for i in range(count)]
    return rights, rights[0] - 62.0


def _header_row(
    page: pymupdf.Page,
    name: str,
    columns: tuple[ColumnSpec, ...],
    rights: list[float],
    y: float,
    unit: str,
    size: float,
) -> None:
    texts = [
        {"entity": c.entity, "period": c.period, "sub": c.sub, "unit": unit}[name] for c in columns
    ]
    if name in ("entity", "period"):  # equal neighbours print once, centred over the group
        i = 0
        while i < len(texts):
            j = i
            while j + 1 < len(texts) and texts[j + 1] == texts[i]:
                j += 1
            text = texts[i]
            if text and j > i:
                left, right = rights[i] - 30.0, rights[j]
                width = pymupdf.get_text_length(text, fontname="hebo", fontsize=size)
                _text(page, (left + right - width) / 2, y, text, size=size, bold=True)
            elif text:
                _right(page, rights[i], y, text, size=size, bold=True)
            i = j + 1
        return
    for right, text in zip(rights, texts, strict=True):
        if text:
            _right(page, right, y, text, size=size - 0.5, bold=True)


def _row(
    page: pymupdf.Page,
    row: Row,
    rights: list[float],
    y: float,
    dx: float,
    note_x: float,
    size: float,
) -> None:
    bold = row.style in ("section", "total")
    if row.label:
        _text(page, dx + LABEL_X, y, row.label, size=size, bold=bold)
    if row.note:
        _text(page, note_x, y, row.note, size=size)
    if row.style in ("subtotal", "total") and row.values:
        for right in rights:
            page.draw_line(
                (right - (40 if len(rights) > 3 else 55), y - 10), (right, y - 10), width=0.5
            )
    if row.values:  # section headers print no figures
        for right, value in zip(rights, row.values, strict=True):
            _right(page, right, y, value, size=size, bold=row.style == "total")
