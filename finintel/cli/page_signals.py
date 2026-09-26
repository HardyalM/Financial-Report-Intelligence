"""Per-page signals for the inspection dump: transparent counts a human can rank pages by.

This is not the statement locator. Scoring weights, scope classification, exclusions and selection
are M2.1 (EXTRACTION section 1). The inspector only counts what is on each page and orders pages
that mention a primary-statement title, so the tech lead can find the statements by eye.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ConfigDict

from finintel.ingest import MIN_EXTRACTABLE_CHARS
from finintel.parse.text_layer import OutlineEntry, PageText, Word

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
TITLE_REGION = 0.25  # top quarter of the page
TITLE_SIZE_RATIO = 1.2  # x the page's median word size
MAX_TITLE_LINES = 5

_KEYWORD_RE = {k: re.compile(rf"\b{re.escape(k)}\b") for k in KEYWORDS}
_NUMERIC = re.compile(
    r"^[(\-\u2013\u2212]?[£$€]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\)?[*\u2020\u2021]?$"
    r"|^[\-\u2013\u2014]$"  # a lone dash prints nil
)
_YEAR = re.compile(r"^(?:19|20)\d{2}$")
_UNIT = re.compile(
    r"(?:us\$|£|\$|€)\s?(?:millions?|mn|m|['\u2019]000|000|k)(?![a-z0-9])|\beurm\b", re.IGNORECASE
)
_LETTER = re.compile(r"[A-Za-z]")


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


def normalise(text: str) -> str:
    """Lower-case, NFKC, straight quotes, collapsed whitespace. For matching, never for storage."""
    text = unicodedata.normalize("NFKC", text).replace("\u2019", "'").replace("\u2018", "'")
    return " ".join(text.lower().split())


def page_signals(page: PageText, outline: Sequence[OutlineEntry]) -> PageSignals:
    words = page.words
    rows = list(visual_rows(words))
    numeric = [w for w in words if _NUMERIC.match(w.text)]
    body = normalise(page.text)
    titles = title_lines(page)
    return PageSignals(
        page=page.page,
        label=page.label,
        chars=page.char_count,
        words=len(words),
        replacement_chars=page.replacement_char_count,
        has_text=page.char_count - page.replacement_char_count >= MIN_EXTRACTABLE_CHARS,
        numeric_token_share=round(len(numeric) / len(words), 4) if words else 0.0,
        numeric_rows=sum(1 for row in rows if sum(bool(_NUMERIC.match(w.text)) for w in row) >= 2),
        header_years=_header_years(rows),
        unit_tokens=tuple(sorted({normalise(m.group(0)) for m in _UNIT.finditer(page.text)})),
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


def visual_rows(words: Sequence[Word]) -> Iterable[list[Word]]:
    """Group words into printed rows by vertical centre. Table cells often sit in separate
    PyMuPDF blocks, so (block, line) ids alone do not give table rows."""
    if not words:
        return
    sizes = sorted(w.size for w in words)
    tolerance = max(2.0, 0.35 * sizes[len(sizes) // 2])
    ordered = sorted(words, key=lambda w: ((w.bbox[1] + w.bbox[3]) / 2, w.bbox[0]))
    row: list[Word] = []
    row_centre = 0.0
    for word in ordered:
        centre = (word.bbox[1] + word.bbox[3]) / 2
        if row and centre - row_centre > tolerance:
            yield sorted(row, key=lambda w: w.bbox[0])
            row = []
        if not row:
            row_centre = centre
        row.append(word)
    yield sorted(row, key=lambda w: w.bbox[0])


def title_lines(page: PageText) -> tuple[str, ...]:
    """Title-like lines: in the top quarter, and larger than the page's median word or bold."""
    median = page.median_word_size
    if median is None:
        return ()
    limit = page.height * TITLE_REGION
    lines = sorted(
        (
            line
            for line in page.lines
            if line.bbox[1] < limit
            and _LETTER.search(line.text)
            and (line.size >= TITLE_SIZE_RATIO * median or line.bold)
        ),
        key=lambda line: (line.bbox[1], line.bbox[0]),
    )
    return tuple(" ".join(line.text.split()) for line in lines[:MAX_TITLE_LINES])


def _header_years(rows: Iterable[list[Word]]) -> tuple[str, ...]:
    years: set[str] = set()
    for row in rows:
        found = [w.text for w in row if _YEAR.match(w.text)]
        if len(found) >= 2:
            years.update(found)
    return tuple(sorted(years, reverse=True))


def statement_hits(text: str) -> list[str]:
    """Primary-statement keywords found in a text (normalised match)."""
    norm = normalise(text)
    return [k for k in STATEMENT_KEYWORDS if _KEYWORD_RE[k].search(norm)]
