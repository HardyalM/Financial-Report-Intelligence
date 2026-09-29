"""Printed folios: the page numbers a reader sees, which differ from PDF page indices.

When the PDF defines page labels, those are the folios. Otherwise (both goldens) the folio is the
number printed in the top or bottom margin. Reports number pages consecutively, so the folio is
`PDF page - offset` for one offset across most of the document; the offset is the one the most
pages agree on, and a page gets a folio only if that number is actually printed in its margin.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from finintel.locate.signals import PageView

MARGIN = 0.08  # top and bottom 8 % of the displayed page
MIN_SUPPORT_SHARE = 0.3  # the offset must be printed on at least this share of pages
MIN_SUPPORT_PAGES = 5
_FOLIO = re.compile(r"^\d{1,4}$")


@dataclass(frozen=True)
class Folios:
    offset: int | None  # printed = PDF page - offset (negative for extracts numbered from 100)
    labels: dict[int, str]  # PDF page -> printed folio (only where printed)

    def label(self, page: int) -> str | None:
        return self.labels.get(page)

    def pdf_page(self, printed: int) -> int | None:
        return printed + self.offset if self.offset is not None else None


def infer_folios(views: Sequence[PageView]) -> Folios:
    margin_numbers: dict[int, set[int]] = {}
    for view in views:
        top, bottom = view.height * MARGIN, view.height * (1 - MARGIN)
        numbers = {
            int(word.text)
            for word, box in view.words
            if (box[3] <= top or box[1] >= bottom) and _FOLIO.match(word.text)
        }
        margin_numbers[view.page.page] = numbers
    votes: Counter[int] = Counter(
        page - n for page, numbers in margin_numbers.items() for n in numbers
    )
    if not votes:
        return Folios(None, {})
    offset, support = votes.most_common(1)[0]
    if support < max(MIN_SUPPORT_PAGES, MIN_SUPPORT_SHARE * len(views)):
        return Folios(None, {})
    labels = {
        page: str(page - offset)
        for page, numbers in margin_numbers.items()
        if page - offset in numbers
    }
    return Folios(offset, labels)
