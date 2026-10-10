"""A small report whose balance sheet is printed in two side-by-side panels on one landscape page
(assets left; liabilities and equity right), as Tesco prints it (company_c p.139). Figures are
fictional and exist only because this file prints them."""

from __future__ import annotations

from pathlib import Path

import pymupdf

PORTRAIT, LANDSCAPE = (595.0, 842.0), (842.0, 595.0)
Line = tuple[str, str | None, str | None]  # label, this year, last year (None: a heading)


def _right(page: pymupdf.Page, x1: float, y: float, text: str, size: float = 8.0) -> None:
    width = pymupdf.get_text_length(text, fontname="helv", fontsize=size)
    page.insert_text((x1 - width, y), text, fontname="helv", fontsize=size)


def _left(
    page: pymupdf.Page, x: float, y: float, text: str, size: float = 8.0, bold: bool = False
) -> None:
    page.insert_text((x, y), text, fontname="hebo" if bold else "helv", fontsize=size)


def _panel(
    page: pymupdf.Page,
    label_x: float,
    cols: tuple[float, float],
    top: float,
    rows: list[Line],
) -> None:
    _right(page, cols[0], top, "2025")
    _right(page, cols[1], top, "2024")
    _right(page, cols[0], top + 10, "£m")
    _right(page, cols[1], top + 10, "£m")
    y = top + 26
    for label, a, b in rows:
        _left(page, label_x, y, label, bold=a is None)
        if a is not None and b is not None:
            _right(page, cols[0], y, a)
            _right(page, cols[1], y, b)
        y += 12


INCOME: list[Line] = [
    ("Revenue", "1,000", "900"),
    ("Operating costs", "(800)", "(750)"),
    ("Operating profit", "200", "150"),
    ("Finance costs", "(10)", "(10)"),
    ("Profit before tax", "190", "140"),
    ("Taxation", "(40)", "(30)"),
    ("Profit for the year", "150", "110"),
]
ASSETS: list[Line] = [
    ("Non-current assets", None, None),
    ("Property, plant and equipment", "500", "480"),
    ("Current assets", None, None),
    ("Inventories", "100", "90"),
    ("Cash and cash equivalents", "50", "40"),
    ("Total current assets", "150", "130"),
    ("Total assets", "650", "610"),
]
LIABILITIES: list[Line] = [
    ("Current liabilities", None, None),
    ("Trade and other payables", "(120)", "(110)"),
    ("Total current liabilities", "(120)", "(110)"),
    ("Non-current liabilities", None, None),
    ("Borrowings", "(230)", "(220)"),
    ("Total liabilities", "(350)", "(330)"),
    ("Net assets", "300", "280"),
    ("Equity", None, None),
    ("Share capital", "100", "100"),
    ("Retained earnings", "200", "180"),
    ("Total equity", "300", "280"),
]


def panel_report(path: Path) -> Path:
    doc = pymupdf.open()
    cover = doc.new_page(width=PORTRAIT[0], height=PORTRAIT[1])
    _left(cover, 60, 80, "Strategic report", size=16, bold=True)
    for i in range(30):
        _left(
            cover,
            60,
            110 + 14 * i,
            "The group sells food and household goods to customers in the United Kingdom.",
        )
    income = doc.new_page(width=PORTRAIT[0], height=PORTRAIT[1])
    _left(income, 60, 70, "Consolidated income statement", size=16, bold=True)
    _left(income, 60, 88, "For the year ended 31 December 2025")
    _panel(income, 60, (420.0, 500.0), 110.0, INCOME)
    balance = doc.new_page(width=LANDSCAPE[0], height=LANDSCAPE[1])
    _left(balance, 40, 50, "Consolidated balance sheet", size=16, bold=True)
    _left(balance, 40, 68, "At 31 December 2025")
    _panel(balance, 40, (330.0, 400.0), 90.0, ASSETS)
    _panel(balance, 440, (720.0, 790.0), 90.0, LIABILITIES)
    for number in range(doc.page_count):
        p = doc[number]
        _right(p, p.rect.width - 30, p.rect.height - 20, str(number + 11))
    doc.set_metadata({"title": "panel report", "producer": "finintel tests"})
    doc.save(path)
    doc.close()
    return path
