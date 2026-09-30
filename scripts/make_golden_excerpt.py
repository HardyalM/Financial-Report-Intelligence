"""Build tests/golden/{stem}/excerpt.pdf from a fixture PDF (OQ-10 = A, ADR-009).

The excerpt keeps the located statement pages (and the parent-company pages, so scope rejection is
tested) at their ORIGINAL page numbers; every other page is blank. A few hundred KB of a public
document lets E1 run in `make test` and CI without the git-ignored full report.

    python scripts/make_golden_excerpt.py company_a 141 143 195 197
"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent


def build(stem: str, pages: list[int]) -> Path:
    source = pymupdf.open(ROOT / "fixtures" / "pdfs" / f"{stem}.pdf")
    out = pymupdf.open()
    for number in range(1, source.page_count + 1):
        if number in pages:
            out.insert_pdf(source, from_page=number - 1, to_page=number - 1)
        else:
            page = source[number - 1]
            out.new_page(width=page.rect.width, height=page.rect.height)
    target = ROOT / "tests" / "golden" / stem / "excerpt.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    out.save(target, garbage=4, deflate=True, clean=True)
    return target


if __name__ == "__main__":
    path = build(sys.argv[1], [int(p) for p in sys.argv[2:]])
    print(f"{path.relative_to(ROOT)}  {path.stat().st_size / 1024:.0f} KB")
