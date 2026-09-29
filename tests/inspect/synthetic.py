"""Synthetic PDFs for inspection tests. Truth is known by construction.

The figures are fictional and exist only because these helpers print them. They are not golden
labels; goldens live in fixtures/expected/ and are written by the tech lead.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pymupdf

A4 = (595.0, 842.0)
LOREM = (
    "The group delivered a resilient performance in a challenging market, supported by a strong "
    "balance sheet and disciplined capital allocation. Revenue grew in every region, and the "
    "board remains focused on cash generation, customer service and long-term value creation. "
)

# Statement pages. Fictional figures, printed exactly as below.
INCOME_ROWS: Sequence[tuple[str, str, str, str]] = (
    ("Revenue", "3", "13,907.5", "12,345.0"),
    ("Cost of sales", "", "(10,321.2)", "(9,210.4)"),
    ("Gross profit", "", "3,586.3", "3,134.6"),
    ("Administrative expenses", "4", "(1,902.1)", "(1,811.9)"),
    ("Other operating income", "", "12.4", "\u2013"),
    ("Operating profit", "5", "1,696.6", "1,322.7"),
    ("Finance income", "7", "40.1", "22.3"),
    ("Finance costs", "7", "(301.9)", "(287.0)"),
    ("Profit before taxation", "", "1,434.8", "1,058.0"),
    ("Taxation", "8", "(358.7)", "(264.5)"),
    ("Profit for the year", "", "1,076.1", "793.5"),
)
BALANCE_ROWS: Sequence[tuple[str, str, str, str]] = (
    ("Non-current assets", "", "", ""),
    ("Property, plant and equipment", "12", "6,120.0", "5,980.3"),
    ("Right-of-use assets", "13", "2,410.2", "2,501.7"),
    ("Intangible assets", "14", "1,003.4", "998.1"),
    ("", "", "9,533.6", "9,480.1"),
    ("Current assets", "", "", ""),
    ("Inventories", "16", "1,245.6", "1,190.2"),
    ("Trade and other receivables", "17", "812.3", "790.4"),
    ("Cash and cash equivalents", "18", "1,340.9", "1,122.8"),
    ("", "", "3,398.8", "3,103.4"),
    ("Current liabilities", "", "", ""),
    ("Trade and other payables", "19", "(3,011.2)", "(2,870.5)"),
    ("Borrowings", "20", "(250.0)", "(400.0)"),
    ("Lease liabilities", "21", "(310.5)", "(298.2)"),
    ("", "", "(3,571.7)", "(3,568.7)"),
    ("Net current liabilities", "", "(172.9)", "(465.3)"),
    ("Total equity", "", "4,820.3", "4,390.0"),
)
COMPANY_ROWS: Sequence[tuple[str, str, str, str]] = (
    ("Investments in subsidiaries", "3", "5,210.0", "5,210.0"),
    ("Amounts owed by group undertakings", "4", "1,020.5", "998.4"),
    ("Total equity", "", "6,230.5", "6,208.4"),
)


# Base-14 Helvetica only encodes Latin-1, so an en dash or a Unicode minus would print as a
# placeholder. Glyphs outside Latin-1 use MuPDF's built-in Droid Sans Fallback instead, which
# writes a proper ToUnicode map, as a typeset annual report would.
_UNICODE_FONT = pymupdf.Font("cjk")


def _text(
    page: pymupdf.Page, x: float, y: float, text: str, size: float = 9, bold: bool = False
) -> None:
    if any(ord(char) > 0xFF for char in text):
        writer = pymupdf.TextWriter(page.rect)
        writer.append((x, y), text, font=_UNICODE_FONT, fontsize=size)
        writer.write_text(page)
    else:
        page.insert_text((x, y), text, fontsize=size, fontname="hebo" if bold else "helv")


def _paragraphs(page: pymupdf.Page, y: float, repeats: int = 3) -> None:
    box = pymupdf.Rect(50, y, 545, y + 400)
    page.insert_textbox(box, LOREM * repeats, fontsize=9, fontname="helv")


def _statement(
    page: pymupdf.Page, title: str, subtitle: str, rows: Sequence[tuple[str, str, str, str]]
) -> None:
    _text(page, 50, 70, title, size=16, bold=True)
    _text(page, 50, 90, subtitle)
    _text(page, 330, 120, "Notes", bold=True)
    _text(page, 400, 120, "2025", bold=True)
    _text(page, 480, 120, "2024", bold=True)
    _text(page, 400, 132, "£m", bold=True)
    _text(page, 480, 132, "£m", bold=True)
    y = 155.0
    for label, note, current, prior in rows:
        is_section = bool(label) and not current
        _text(page, 50, y, label, bold=is_section or label.startswith(("Total", "Profit for")))
        if note:
            _text(page, 330, y, note)
        if current:
            _text(page, 400, y, current)
            _text(page, 480, y, prior)
        if not label and current:  # unlabelled subtotal: ruled above
            page.draw_line((395, y - 11), (545, y - 11), width=0.5)
        y += 18
    _paragraphs(page, y + 20, repeats=1)


def mini_report(path: Path, *, blank_pages: int = 0) -> Path:
    """A seven-page annual report: cover, narrative, contents-free statements, notes.

    PDF page -> content (1-based):
      1 cover (label i)            2 chief executive's review (label ii)
      3 consolidated income statement (label 140)
      4 consolidated balance sheet (label 141)
      5 company balance sheet (label 142)
      6 notes to the consolidated financial statements (label 143)
      7 glossary (label 144)
    `blank_pages` appends image-free empty pages (to fail the digital-born check).
    """
    doc = pymupdf.open()
    cover = doc.new_page(width=A4[0], height=A4[1])
    _text(cover, 50, 120, "Example Group plc", size=28, bold=True)
    _text(cover, 50, 160, "Annual Report and Accounts 2025", size=18)
    _paragraphs(cover, 200)

    review = doc.new_page(width=A4[0], height=A4[1])
    _text(review, 50, 70, "Chief Executive's review", size=16, bold=True)
    _paragraphs(review, 100, repeats=4)
    _text(review, 50, 520, "See the consolidated income statement for statutory results.")

    _statement(
        doc.new_page(width=A4[0], height=A4[1]),
        "Consolidated income statement",
        "For the 52 weeks ended 29 March 2025",
        INCOME_ROWS,
    )
    _statement(
        doc.new_page(width=A4[0], height=A4[1]),
        "Consolidated balance sheet",
        "As at 29 March 2025",
        BALANCE_ROWS,
    )
    _statement(
        doc.new_page(width=A4[0], height=A4[1]),
        "Company balance sheet",
        "As at 29 March 2025",
        COMPANY_ROWS,
    )
    notes = doc.new_page(width=A4[0], height=A4[1])
    _text(notes, 50, 70, "Notes to the consolidated financial statements", size=14, bold=True)
    _paragraphs(notes, 100, repeats=4)
    glossary = doc.new_page(width=A4[0], height=A4[1])
    _text(glossary, 50, 70, "Glossary", size=14, bold=True)
    _paragraphs(glossary, 100, repeats=4)
    for _ in range(blank_pages):
        doc.new_page(width=A4[0], height=A4[1])

    doc.set_toc(
        [
            [1, "Strategic report", 2],
            [1, "Financial statements", 3],
            [2, "Consolidated income statement", 3],
            [2, "Consolidated balance sheet", 4],
            [2, "Company balance sheet", 5],
            [2, "Notes to the financial statements", 6],
        ]
    )
    doc.set_page_labels(
        [
            {"startpage": 0, "prefix": "", "style": "r", "firstpagenum": 1},
            {"startpage": 2, "prefix": "", "style": "D", "firstpagenum": 140},
        ]
    )
    doc.set_metadata(
        {"title": "Example Group plc Annual Report 2025", "producer": "finintel tests"}
    )
    doc.save(path)
    doc.close()
    return path


def ruled_table_pdf(path: Path) -> Path:
    """One page with a fully ruled 3x3 table, for pdfplumber's "lines" strategy."""
    doc = pymupdf.open()
    page = doc.new_page(width=A4[0], height=A4[1])
    xs, ys = (50.0, 250.0, 350.0, 450.0), (100.0, 120.0, 140.0, 160.0)
    for x in xs:
        page.draw_line((x, ys[0]), (x, ys[-1]))
    for y in ys:
        page.draw_line((xs[0], y), (xs[-1], y))
    cells = (
        ("Item", "2025", "2024"),
        ("Revenue", "13,907.5", "12,345.0"),
        ("Borrowings", "(250.0)", "\u2013"),
    )
    for r, row in enumerate(cells):
        for c, text in enumerate(row):
            _text(page, xs[c] + 3, ys[r] + 14, text)
    doc.save(path)
    doc.close()
    return path


def encrypted_pdf(path: Path, *, user_password: str | None) -> Path:
    """A one-page PDF with AES-256 encryption; `user_password=None` means owner password only."""
    doc = pymupdf.open()
    page = doc.new_page(width=A4[0], height=A4[1])
    _paragraphs(page, 60)
    doc.save(
        path,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,  # type: ignore[attr-defined]  # not in PyMuPDF's hints
        owner_pw="owner-secret",
        user_pw=user_password or "",
        permissions=pymupdf.PDF_PERM_PRINT,  # type: ignore[attr-defined]  # not in PyMuPDF's hints
    )
    doc.close()
    return path


def rotated_pdf(path: Path, rotation: int) -> Path:
    """One page with a word near the unrotated top-left, displayed with /Rotate `rotation`."""
    doc = pymupdf.open()
    page = doc.new_page(width=A4[0], height=A4[1])
    page.insert_text((60, 70), "Title", fontsize=14)
    page.set_rotation(rotation)
    doc.save(path)
    doc.close()
    return path


def display_bbox(path: Path, bbox: tuple[float, float, float, float]) -> tuple[float, ...]:
    """Where PyMuPDF itself displays an unrotated box on page 1 (the ground truth)."""
    with pymupdf.open(path) as doc:
        rect = pymupdf.Rect(bbox) * doc[0].rotation_matrix
        return (rect.x0, rect.y0, rect.x1, rect.y1)
