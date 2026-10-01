"""Running headers, footers and folios: signals, never content (RAG section 1.1).

A line is margin furniture if it sits in the top or bottom band and either is only a number (a
folio) or repeats, digits masked, on at least 30 % of the pages. Navigation bars in the title
region are handled by the locator's chrome detector and combined here.
"""

from __future__ import annotations

import re
from collections import Counter

from finintel.locate.signals import PageView, detect_chrome, normalise
from finintel.parse.text_layer import TextLayer

MARGIN = 0.08  # top and bottom 8 % of the displayed page
REPEAT_SHARE = 0.30
MIN_PAGES = 3
_DIGITS = re.compile(r"\d+")
_FOLIO = re.compile(r"^[\s\d]+$")


def mask(text: str) -> str:
    return _DIGITS.sub("#", normalise(text))


def furniture(layer: TextLayer) -> frozenset[str]:
    """Masked texts that are furniture wherever they appear in a margin band."""
    seen: Counter[str] = Counter()
    for page in layer.pages:
        view = PageView(page)
        bands = {
            mask(v.text)
            for v in (*view.band(MARGIN), *view.band(MARGIN, bottom=True))
            if v.text.strip()
        }
        seen.update(bands)
    threshold = max(MIN_PAGES, REPEAT_SHARE * layer.page_count)
    repeated = {text for text, n in seen.items() if n >= threshold}
    return frozenset(repeated | {mask(c) for c in detect_chrome(layer)})


def is_furniture(text: str, y0: float, y1: float, height: float, repeated: frozenset[str]) -> bool:
    in_margin = y1 <= height * MARGIN or y0 >= height * (1 - MARGIN)
    if in_margin and _FOLIO.match(text):
        return True
    return mask(text) in repeated and (in_margin or y1 <= height * 0.25)
