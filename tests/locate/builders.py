"""Hand-built text layers for locator unit tests, and a spec-to-result helper.

Unit tests describe a page as printed lines; `page()` turns them into the same `PageText` the
PyMuPDF reader produces (words split on spaces, one line per entry), so tests exercise the real
locator code without a PDF. End-to-end tests render a spec instead (`locate_spec`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evals.synthetic.render import render
from evals.synthetic.spec import Spec, check_spec
from finintel.locate import LocateResult, locate
from finintel.parse.text_layer import Line, OutlineEntry, PageText, TextLayer, Word, read_text_layer

CHAR_WIDTH = 0.5  # of the font size: close enough for layout tests


@dataclass(frozen=True)
class Printed:
    text: str
    x: float
    y: float  # baseline-ish top of the line
    size: float = 8.0
    bold: bool = False


def page(
    lines: Sequence[Printed],
    *,
    number: int = 1,
    label: str | None = None,
    width: float = 595.0,
    height: float = 842.0,
    rotation: int = 0,
) -> PageText:
    words: list[Word] = []
    out_lines: list[Line] = []
    for index, printed in enumerate(lines):
        x = printed.x
        for token in printed.text.split():
            w = len(token) * printed.size * CHAR_WIDTH
            words.append(
                Word(
                    text=token,
                    bbox=(x, printed.y, x + w, printed.y + printed.size),
                    block=index,
                    line=0,
                    font="Helvetica-Bold" if printed.bold else "Helvetica",
                    size=printed.size,
                    bold=printed.bold,
                )
            )
            x += w + printed.size * CHAR_WIDTH
        out_lines.append(
            Line(
                block=index,
                line=0,
                bbox=(printed.x, printed.y, x, printed.y + printed.size),
                text=printed.text,
                size=printed.size,
                bold=printed.bold,
            )
        )
    return PageText(
        page=number,
        label=label,
        width=width,
        height=height,
        rotation=rotation,
        words=tuple(words),
        lines=tuple(out_lines),
        char_count=sum(len(w.text) for w in words),
    )


def layer(pages: Sequence[PageText], outline: Sequence[OutlineEntry] = ()) -> TextLayer:
    return TextLayer(
        extractor="test",
        page_count=len(pages),
        has_page_labels=any(p.label for p in pages),
        outline=tuple(outline),
        pages=tuple(pages),
    )


def locate_spec(spec: Spec | dict[str, Any], tmp_path: Path) -> LocateResult:
    """Validate, render and locate a spec (a Spec, or a dict in the YAML shape)."""
    model = spec if isinstance(spec, Spec) else Spec.model_validate(spec)
    check_spec(model)
    pdf = render(model, tmp_path / f"{model.name}.pdf")
    return locate(read_text_layer(pdf))
