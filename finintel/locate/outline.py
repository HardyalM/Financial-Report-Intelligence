"""Bookmarks and the printed contents page as location evidence (EXTRACTION section 1.1).

- Bookmark hit: a PDF bookmark whose title is a statement title points at the page.
- Contents hit: a line on a contents page names a statement and its printed folio, which maps to
  a PDF page through the folio offset (or page labels).
- Section path: the chain of bookmarks enclosing a page, used for scope and exclusions.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from finintel.locate.folios import Folios
from finintel.locate.signals import PageView
from finintel.locate.titles import TitleMatch, match_title
from finintel.parse.text_layer import OutlineEntry, TextLayer

_CONTENTS_TITLE = re.compile(r"^(?:table of )?contents$|^in this report$")
_LEADING_FOLIO = re.compile(r"^(?P<folio>\d{1,3})\s+(?P<title>\D.*)$")
_TRAILING_FOLIO = re.compile(r"^(?P<title>.*?\D)[\s.\u00b7\u2026]*(?P<folio>\d{1,3})$")


@dataclass(frozen=True)
class LocationHint:
    match: TitleMatch
    source: str  # human-readable: 'bookmark "Balance sheet"' or 'contents p.3 "... 140"'


def section_paths(outline: Sequence[OutlineEntry], page_count: int) -> dict[int, tuple[str, ...]]:
    """For every page, the titles of the bookmarks enclosing it, outermost first."""
    chains: list[tuple[int, tuple[str, ...]]] = []
    stack: list[tuple[int, str]] = []
    for entry in outline:
        while stack and stack[-1][0] >= entry.level:
            stack.pop()
        stack.append((entry.level, entry.title))
        if entry.page is not None:
            chains.append((entry.page, tuple(title for _, title in stack)))
    chains.sort(key=lambda item: item[0])  # stable: document order kept within a page
    paths: dict[int, tuple[str, ...]] = {}
    index = 0
    current: tuple[str, ...] = ()
    for page in range(1, page_count + 1):
        while index < len(chains) and chains[index][0] <= page:
            current = chains[index][1]
            index += 1
        paths[page] = current
    return paths


def bookmark_hints(outline: Sequence[OutlineEntry]) -> dict[int, list[LocationHint]]:
    hints: dict[int, list[LocationHint]] = defaultdict(list)
    for entry in outline:
        match = match_title(entry.title)
        if match is not None and entry.page is not None:
            hints[entry.page].append(LocationHint(match, f'bookmark "{entry.title}"'))
    return hints


def contents_hints(
    views: Sequence[PageView], folios: Folios, layer: TextLayer
) -> dict[int, list[LocationHint]]:
    """Statement titles listed on contents pages, mapped to the PDF pages they point at."""
    labels = {p.label: p.page for p in layer.pages if p.label}
    hints: dict[int, list[LocationHint]] = defaultdict(list)
    for view in views:
        if not any(_CONTENTS_TITLE.match(v.norm) for v in view.title_lines):
            continue
        for line in view.lines:
            parsed = _LEADING_FOLIO.match(line.text) or _TRAILING_FOLIO.match(line.text)
            if not parsed:
                continue
            match = match_title(parsed.group("title").strip(" .\u00b7\u2026"))
            printed = parsed.group("folio")
            target = labels.get(printed) or folios.pdf_page(int(printed))
            if match is None or target is None or not 1 <= target <= layer.page_count:
                continue
            source = f'contents p.{view.page.page} "{line.text}"'
            hints[target].append(LocationHint(match, source))
    return hints
