"""Synthetic narrative PDFs with known truth, and a helper to chunk them."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pymupdf

from finintel.narrative import Chunk, build_chunks
from finintel.parse.text_layer import read_text_layer

SHA = "ab" * 32
FILLER = (
    "The group continued to invest in its brands and supply chain during the year, and "
    "management reviewed the carrying value of each cash generating unit against its "
    "forecast cash flows. "
)


def sentences(tag: str, count: int) -> str:
    """`count` distinct sentences, each containing the unique token `tag-N`."""
    return " ".join(
        f"Item {tag}-{n} was reviewed by the board and recorded in the minutes."
        for n in range(count)
    )


Item = tuple[
    str, Any
]  # ("h", text) | ("h2", text) | ("p", text) | ("table", rows) | ("foot", text)


def make_pdf(
    path: Path, pages: Sequence[Sequence[Item]], outline: Sequence[tuple[int, str, int]] = ()
) -> Path:
    """A report with a running header and a folio on every page. Items are laid out top down."""
    doc = pymupdf.open()
    for number, items in enumerate(pages, start=1):
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 28), "EXAMPLE PLC ANNUAL REPORT", fontsize=7, fontname="helv")
        page.insert_text((290, 826), str(number + 40), fontsize=8, fontname="helv")
        y = 70.0
        for kind, value in items:
            if kind == "h":
                page.insert_text((50, y + 14), value, fontsize=16, fontname="hebo")
                y += 34
            elif kind == "h2":
                page.insert_text((50, y + 11), value, fontsize=12, fontname="hebo")
                y += 26
            elif kind == "p":
                height = 12.0 * (len(value) // 92 + 2)
                page.insert_textbox(
                    pymupdf.Rect(50, y, 545, y + height), value, fontsize=9, fontname="helv"
                )
                y += height + 8
            elif kind == "table":
                for row in value:
                    page.insert_text((50, y + 9), row[0], fontsize=9, fontname="helv")
                    for i, cell in enumerate(row[1:]):
                        right = 380 + 70 * i
                        width = pymupdf.get_text_length(cell, fontname="helv", fontsize=9)
                        page.insert_text((right - width, y + 9), cell, fontsize=9, fontname="helv")
                    y += 13
                y += 10
            elif kind == "foot":
                page.insert_text((50, 790), value, fontsize=6.5, fontname="helv")
    if outline:
        doc.set_toc([list(e) for e in outline])
    doc.save(path)
    doc.close()
    return path


def chunk(path: Path, **kwargs: Any) -> list[Chunk]:
    return build_chunks(read_text_layer(path), document_sha256=SHA, **kwargs)


def build(
    tmp_path: Path,
    pages: Sequence[Sequence[Item]],
    outline: Sequence[tuple[int, str, int]] = (),
    **kwargs: Any,
) -> list[Chunk]:
    return chunk(make_pdf(tmp_path / "r.pdf", pages, outline), **kwargs)


def by_text(chunks: Sequence[Chunk], token: str) -> Chunk:
    [found] = [c for c in chunks if token in c.text]
    return found


def excluded_map(**pages: str) -> Mapping[int, str]:
    return {int(k.removeprefix("p")): v for k, v in pages.items()}
