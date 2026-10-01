"""Synthetic pages with known tables, so each layout rule is tested in isolation."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pymupdf

from finintel.parse.text_layer import TextLayer, read_text_layer

Cell = tuple[str, float, str]  # text, x, align: "l" | "r"
PACK = {
    "periods": [
        {"id": "FY2024", "label": "2024", "end_date": "2024-12-31"},
        {"id": "FY2023", "label": "2023", "end_date": "2023-12-31"},
    ]
}


def make_pdf(path: Path, pages: Sequence[Sequence[tuple[float, Sequence[Cell]]]]) -> Path:
    """Each page is a list of (y, cells). Right-aligned cells end at x; left-aligned start at x."""
    doc = pymupdf.open()
    for rows in pages:
        page = doc.new_page(width=595, height=842)
        for y, cells in rows:
            for text, x, align in cells:
                width = pymupdf.get_text_length(text, fontname="helv", fontsize=9)
                page.insert_text(
                    (x - width if align == "r" else x, y), text, fontsize=9, fontname="helv"
                )
    doc.save(path)
    doc.close()
    return path


def layer(tmp_path: Path, pages: Sequence[Sequence[tuple[float, Sequence[Cell]]]]) -> TextLayer:
    return read_text_layer(make_pdf(tmp_path / "t.pdf", pages))


def period_table(label: str, first: str, second: str, *, unit: bool = True, note: str | None = None,
                 tag: bool = False, y0: float = 100.0) -> list[tuple[float, list[Cell]]]:  # fmt: skip
    """A "GBP million | 2024 | 2023" table, one data row, figures right-aligned under cells."""
    rows: list[tuple[float, list[Cell]]] = []
    if unit:
        rows.append((y0, [("£ million", 380, "r"), ("£ million", 460, "r")]))
    head: list[Cell] = [("2024", 380, "r"), ("2023", 440 if tag else 460, "r")]
    if tag:
        head.append(("(re-presented)", 500, "r"))
    rows.append((y0 + 12, head))
    data: list[Cell] = [(label, 50, "l")]
    if note:
        data.append((note, 330, "r"))
    data += [(first, 380, "r"), (second, 500 if tag else 460, "r")]
    rows.append((y0 + 36, data))
    return rows
