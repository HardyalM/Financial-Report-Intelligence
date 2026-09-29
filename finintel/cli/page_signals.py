"""Per-page signals for the inspection dump: transparent counts a human can rank pages by.

This is not the statement locator (finintel.locate, M2.1): no scope, no exclusions, no selection.
It reuses the locator's page primitives (finintel.locate.signals), so the counts in an inspection
dump are the same facts the locator scores with.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ConfigDict

from finintel.ingest import MIN_EXTRACTABLE_CHARS
from finintel.locate.signals import PageView, normalise
from finintel.parse.text_layer import OutlineEntry, PageText

#: Primary-statement title phrases; these drive the inspection ranking.
STATEMENT_KEYWORDS: tuple[str, ...] = (
    "income statement",
    "statement of profit",  # also matches "statement of profit or loss"
    "statement of comprehensive income",
    "balance sheet",
    "statement of financial position",
)
#: Counted and reported, but not used for ranking.
OTHER_KEYWORDS: tuple[str, ...] = (
    "statement of cash flows",
    "cash flow statement",
    "statement of changes in equity",
    "notes to the",
)
KEYWORDS = STATEMENT_KEYWORDS + OTHER_KEYWORDS

# EXTRACTION section 1.1 thresholds, reused here only to describe a page as "table-like".
NUMERIC_SHARE_TABLE = 0.30
NUMERIC_ROWS_TABLE = 8
MAX_TITLE_LINES = 5

_KEYWORD_RE = {k: re.compile(rf"\b{re.escape(k)}\b") for k in KEYWORDS}


class PageSignals(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    page: int
    label: str | None
    chars: int
    words: int
    replacement_chars: int
    has_text: bool
    numeric_token_share: float
    numeric_rows: int
    header_years: tuple[str, ...]
    unit_tokens: tuple[str, ...]
    keyword_hits: dict[str, int]
    title_lines: tuple[str, ...]
    title_keyword_hits: tuple[str, ...]
    outline_titles: tuple[str, ...]
    error: str | None

    @property
    def mentions_statement(self) -> bool:
        return bool(
            self.title_keyword_hits
            or any(self.keyword_hits[k] for k in STATEMENT_KEYWORDS)
            or statement_hits(" ".join(self.outline_titles))
        )

    @property
    def titled_as_statement(self) -> bool:
        return bool(self.title_keyword_hits or statement_hits(" ".join(self.outline_titles)))

    @property
    def table_like(self) -> bool:
        return (
            self.numeric_token_share >= NUMERIC_SHARE_TABLE
            and self.numeric_rows >= NUMERIC_ROWS_TABLE
        )


def page_signals(page: PageText, outline: Sequence[OutlineEntry]) -> PageSignals:
    view = PageView(page)
    titles = tuple(line.text for line in view.title_lines[:MAX_TITLE_LINES])
    body = normalise(page.text)
    return PageSignals(
        page=page.page,
        label=page.label,
        chars=page.char_count,
        words=len(page.words),
        replacement_chars=page.replacement_char_count,
        has_text=page.char_count - page.replacement_char_count >= MIN_EXTRACTABLE_CHARS,
        numeric_token_share=view.numeric_share,
        numeric_rows=view.numeric_rows,
        header_years=view.header_years,
        unit_tokens=view.unit_tokens,
        keyword_hits={k: len(rx.findall(body)) for k, rx in _KEYWORD_RE.items()},
        title_lines=titles,
        title_keyword_hits=tuple(statement_hits(" ".join(titles))),
        outline_titles=tuple(e.title for e in outline if e.page == page.page),
        error=page.error,
    )


def rank_pages(signals: Iterable[PageSignals]) -> list[PageSignals]:
    """Pages that mention a statement title, most statement-like first.

    Order: titled as a statement (title region or bookmark), then table-like, then more numeric
    rows, then more body mentions, then page number. Every key is a printed count.
    """
    candidates = [s for s in signals if s.mentions_statement]
    return sorted(
        candidates,
        key=lambda s: (
            not s.titled_as_statement,
            not s.table_like,
            -s.numeric_rows,
            -sum(s.keyword_hits[k] for k in STATEMENT_KEYWORDS),
            s.page,
        ),
    )


def statement_hits(text: str) -> list[str]:
    """Primary-statement keywords found in a text (normalised match)."""
    norm = normalise(text)
    return [k for k in STATEMENT_KEYWORDS if _KEYWORD_RE[k].search(norm)]
