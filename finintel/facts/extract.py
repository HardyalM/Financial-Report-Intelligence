"""Read supplemental facts from printed table rows (geometry only, no model, no page given).

For each fact spec, every page is scanned for a row whose label matches. The row's numbers are
placed under their column header by right-edge alignment (the way a reader does): period headers
("2024", "FY24") for ordinary rows, a column label ("Ice Cream") plus the block's period row for a
segment table. The unit ("€ million") comes from the header rows above, or from a suffix printed on
the figure ("€88,035m"). A figure is accepted only when row, column, period and unit are all read;
otherwise it is a warning, never a guess. Occurrences on several pages must agree to within printed
rounding; disagreement gives a null and a warning.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from finintel.facts.models import FactWarning, Source, SupplementalFact, SupplementalFacts
from finintel.parse.text_layer import PageText, TextLayer

ROW_TOLERANCE = 2.5  # pt: words whose vertical centres are this close share a row
ALIGN_TOLERANCE = 10.0  # pt: a figure sits under a header when their right edges are this close
HEADER_ROWS = 45  # how far above a data row its header may be
BASE_CONFIDENCE = 0.90
AGREEMENT_BONUS = 0.05
MAX_CONFIDENCE = 0.99

_NUMBER = re.compile(
    r"^(?P<open>\()?(?P<cur>[€£$])?(?P<int>\d{1,3}(?:,\d{3})+|\d+)(?P<dec>\.\d+)?"
    r"(?P<suffix>m|bn)?(?P<close>\))?$"
)
_PERIOD = re.compile(r"^(?:FY(?P<short>\d{2})|(?P<year>(?:19|20)\d{2}))$")
_UNIT = re.compile(r"([€£$])\s*(million|m|billion|bn)\b", re.IGNORECASE)
_SCALE = {"million": 1_000_000, "m": 1_000_000, "billion": 1_000_000_000, "bn": 1_000_000_000}
_CURRENCY = {"€": "EUR", "£": "GBP", "$": "USD"}


@dataclass(frozen=True)
class FactSpec:
    id: str
    label: str
    row: re.Pattern[str]  # matched against the normalised row label
    kind: str  # "row" | "segment_cell"
    per_share: bool = False
    is_apm: bool = False
    entity: str = "group"
    column: tuple[str, ...] = ()  # segment_cell: the column label's words


def _spec(id_: str, label: str, pattern: str, **kw: object) -> FactSpec:
    return FactSpec(id_, label, re.compile(pattern), **kw)  # type: ignore[arg-type]


SPECS: tuple[FactSpec, ...] = (
    _spec("basic_eps", "Basic earnings per share", r"^basic earnings per share$", kind="row",
          per_share=True),
    _spec("free_cash_flow", "Free cash flow", r"^free cash flow$", kind="row", is_apm=True),
    _spec("underlying_operating_profit", "Underlying operating profit",
          r"^underlying operating profit$", kind="row", is_apm=True),
    _spec("ice_cream_operating_profit", "Ice Cream operating profit", r"^operating profit$",
          kind="segment_cell", entity="segment:Ice Cream", column=("ice", "cream")),
    _spec("parent_investment_in_subsidiaries", "Investments in subsidiaries (parent)",
          r"^investments? in subsidiaries$", kind="row", entity="parent"),
)  # fmt: skip


@dataclass(frozen=True)
class Tok:
    text: str
    x0: float
    x1: float


@dataclass
class Row:
    y: float
    toks: list[Tok]

    @property
    def text(self) -> str:
        return " ".join(t.text for t in self.toks)


@dataclass(frozen=True)
class Candidate:
    fact: str
    year: int
    value: Decimal  # as printed, in `scale` units
    scale: int
    precision: Decimal  # one printed unit of the last digit, in base currency units
    currency: str | None
    page: int
    raw: str
    row_text: str

    @property
    def amount(self) -> Decimal:
        return self.value * self.scale


def page_rows(page: PageText) -> list[Row]:
    words = sorted(page.words, key=lambda w: ((w.bbox[1] + w.bbox[3]) / 2, w.bbox[0]))
    rows: list[Row] = []
    for w in words:
        yc = (w.bbox[1] + w.bbox[3]) / 2
        if rows and abs(rows[-1].y - yc) <= ROW_TOLERANCE:
            rows[-1].toks.append(Tok(w.text, w.bbox[0], w.bbox[2]))
        else:
            rows.append(Row(yc, [Tok(w.text, w.bbox[0], w.bbox[2])]))
    for r in rows:
        r.toks.sort(key=lambda t: t.x0)
    return rows


def parse_number(text: str) -> tuple[Decimal, int, str | None, str | None] | None:
    """(value, decimals, suffix "m"|"bn", currency) for a printed figure, else None."""
    m = _NUMBER.match(text)
    if m is None or bool(m.group("open")) != bool(m.group("close")):
        return None
    dec = m.group("dec") or ""
    value = Decimal(m.group("int").replace(",", "") + dec)
    if m.group("open"):
        value = -value
    return value, len(dec) - 1 if dec else 0, m.group("suffix"), m.group("cur")


def period_year(text: str) -> int | None:
    m = _PERIOD.match(text.strip("()"))
    if m is None:
        return None
    return int(m.group("year")) if m.group("year") else 2000 + int(m.group("short"))


def normalise_label(tokens: Iterable[str]) -> str:
    text = " ".join(tokens).lower()
    text = re.sub(r"\([^)]*\)", " ", text).replace("*", " ")
    return " ".join(text.split())


def _split(row: Row) -> tuple[list[Tok], list[Tok]]:
    """(label tokens, figure tokens). The label ends at the first figure or percentage."""
    for i, t in enumerate(row.toks):
        if parse_number(t.text) is not None or t.text.endswith("%"):
            return row.toks[:i], row.toks[i:]
    return row.toks, []


def _is_figure(text: str) -> bool:
    """A data figure, not a day-of-month or a note number: has separators, decimals or 3+ digits."""
    parsed = parse_number(text)
    return parsed is not None and (
        len(text.strip("()\u20ac\u00a3$")) >= 3 or "," in text or "." in text
    )


def _period_header(rows: Sequence[Row], at: int) -> list[tuple[int, Tok]] | None:
    """(year, header cell) columns of the nearest period-header row above `at`. A cell runs on
    over a trailing tag such as "(re-presented)", so the figure sits under the whole cell."""
    for j in range(at - 1, max(-1, at - HEADER_ROWS - 1), -1):
        toks = rows[j].toks
        cols: list[tuple[int, Tok]] = []
        for k, t in enumerate(toks):
            year = period_year(t.text)
            if year is None:
                continue
            end = t.x1
            if k + 1 < len(toks) and toks[k + 1].text.startswith("("):
                end = toks[k + 1].x1
            cols.append((year, Tok(t.text, t.x0, end)))
        others = [t for t in toks if period_year(t.text) is None and _is_figure(t.text)]
        if len(cols) >= 2 and not others:
            return cols
    return None


def _unit_above(rows: Sequence[Row], at: int, x1: float | None = None) -> tuple[int, str] | None:
    """(scale, currency symbol) from the nearest "\u20ac million" at or above row `at`; if `x1` is
    given, only a unit whose right edge sits under the same column counts."""
    for j in range(at, max(-1, at - HEADER_ROWS - 1), -1):
        toks = rows[j].toks
        for k in range(len(toks) - 1):
            m = _UNIT.fullmatch(f"{toks[k].text} {toks[k + 1].text}")
            if m is None:
                continue
            if x1 is not None and abs(toks[k + 1].x1 - x1) > ALIGN_TOLERANCE:
                continue
            return _SCALE[m.group(2).lower()], m.group(1)
    return None


def _gap(fig: Tok, head: Tok) -> float:
    """How far a figure sits from a header cell: the best of left edges, right edges, centres."""
    return min(
        abs(fig.x0 - head.x0),
        abs(fig.x1 - head.x1),
        abs((fig.x0 + fig.x1) / 2 - (head.x0 + head.x1) / 2),
    )


def _assign(figs: Sequence[Tok], cols: Sequence[tuple[int, Tok]]) -> dict[int, Tok] | None:
    """year -> figure token, by alignment under the header cell; None if any column is unplaced."""
    placed: dict[int, Tok] = {}
    used: set[int] = set()
    for year, head in cols:
        close = [
            (_gap(f, head), i) for i, f in enumerate(figs)
            if i not in used and _gap(f, head) <= ALIGN_TOLERANCE
        ]  # fmt: skip
        if not close:
            return None
        _, i = min(close)
        used.add(i)
        placed[year] = figs[i]
    return placed


def _candidate(
    spec: FactSpec, year: int, tok: Tok, scale: int, symbol: str | None, page: int, row: Row
) -> Candidate | None:
    parsed = parse_number(tok.text)
    if parsed is None:
        return None
    value, decimals, suffix, cur = parsed
    if spec.per_share:
        scale = 1
    elif suffix:
        scale = _SCALE[suffix]
    precision = (Decimal(1).scaleb(-decimals)) * scale
    sym = cur or symbol
    return Candidate(
        spec.id, year, value, scale, precision, _CURRENCY.get(sym or ""), page, tok.text, row.text
    )


def _row_candidates(spec: FactSpec, rows: Sequence[Row], page: int) -> list[Candidate]:
    out: list[Candidate] = []
    for i, row in enumerate(rows):
        label, figs = _split(row)
        if not figs or not spec.row.match(normalise_label(t.text for t in label)):
            continue
        cols = _period_header(rows, i)
        if cols is None:
            continue
        numbers = [f for f in figs if parse_number(f.text) is not None]
        placed = _assign(numbers, cols)
        if placed is None:
            continue
        unit = _unit_above(rows, i)
        label_text = " ".join(t.text for t in label)
        symbol = unit[1] if unit else None
        if spec.per_share:
            paren = re.search(r"\(([€£$])\)", label_text)
            symbol = paren.group(1) if paren else symbol
        for year, tok in placed.items():
            suffix = parse_number(tok.text)
            has_suffix = bool(suffix and suffix[2])
            if not spec.per_share and unit is None and not has_suffix:
                continue  # no unit read: not a figure we can state
            cand = _candidate(spec, year, tok, unit[0] if unit else 1, symbol, page, row)
            if cand is not None:
                out.append(cand)
    return out


def _segment_candidates(spec: FactSpec, rows: Sequence[Row], page: int) -> list[Candidate]:
    out: list[Candidate] = []
    for i, row in enumerate(rows):
        label, figs = _split(row)
        if not figs or not spec.row.match(normalise_label(t.text for t in label)):
            continue
        head = _column_header(spec.column, rows, i)
        if head is None:
            continue
        h_row, x1 = head
        period = _block_period(rows, i, h_row)
        near = [f for f in figs if abs(f.x1 - x1) <= ALIGN_TOLERANCE and parse_number(f.text)]
        if period is None or len(near) != 1:
            continue
        unit = _unit_above(rows, h_row + 1, x1)
        if unit is None:
            continue
        cand = _candidate(spec, period, near[0], unit[0], unit[1], page, row)
        if cand is not None:
            out.append(cand)
    return out


def _column_header(words: Sequence[str], rows: Sequence[Row], at: int) -> tuple[int, float] | None:
    """(row index, right edge) of the nearest header cell spelled `words` above `at`."""
    for j in range(at - 1, max(-1, at - HEADER_ROWS - 1), -1):
        toks = rows[j].toks
        for k in range(len(toks) - len(words) + 1):
            window = [re.sub(r"\W", "", t.text).lower() for t in toks[k : k + len(words)]]
            if window == list(words):
                return j, toks[k + len(words) - 1].x1
    return None


def _block_period(rows: Sequence[Row], at: int, header_row: int) -> int | None:
    """The period named by the nearest row above `at` (and below the header) that is one year."""
    for j in range(at - 1, header_row, -1):
        if len(rows[j].toks) == 1 and (y := period_year(rows[j].toks[0].text)) is not None:
            return y
    return None


def _candidates(layer: TextLayer, spec: FactSpec) -> list[Candidate]:
    out: list[Candidate] = []
    for page in layer.pages:
        if page.rotation:
            continue
        rows = page_rows(page)
        found = (
            _segment_candidates(spec, rows, page.page)
            if spec.kind == "segment_cell"
            else _row_candidates(spec, rows, page.page)
        )
        out.extend(found)
    return out


def _agree(a: Candidate, b: Candidate) -> bool:
    """Equal to within the coarser printed rounding (6,932m and EUR6.9bn agree)."""
    return abs(a.amount - b.amount) <= (a.precision + b.precision) / 2


def _period_ids(pack: Mapping[str, object]) -> dict[int, str]:
    ids: dict[int, str] = {}
    periods = pack.get("periods", [])
    for p in periods if isinstance(periods, list) else []:
        for text in (p.get("end_date"), p.get("label")):
            if text and str(text)[:4].isdigit():
                ids.setdefault(int(str(text)[:4]), p["id"])
    return ids


def extract_facts(layer: TextLayer, pack: Mapping[str, object]) -> SupplementalFacts:
    """Supplemental facts for the pack's periods, with a warning for everything not safely read."""
    periods = _period_ids(pack)
    facts: list[SupplementalFact] = []
    warnings: list[FactWarning] = []
    for spec in SPECS:
        cands = [c for c in _candidates(layer, spec) if c.year in periods]
        if not cands:
            message = f"no printed row for {spec.label!r} with a readable column and unit"
            warnings.append(FactWarning(code="not_found", fact=spec.id, message=message))
            continue
        for year in sorted({c.year for c in cands}, reverse=True):
            group = [c for c in cands if c.year == year]
            facts.append(_resolve(spec, periods[year], group, warnings))
    return SupplementalFacts(facts=tuple(facts), warnings=tuple(warnings))


def _source(c: Candidate) -> Source:
    return Source(page=c.page, raw_text=c.raw, row_text=c.row_text)


def _resolve(
    spec: FactSpec, period_id: str, group: list[Candidate], warnings: list[FactWarning]
) -> SupplementalFact:
    best = min(group, key=lambda c: (c.precision, c.page))
    agreeing = [c for c in group if _agree(best, c)]
    common: dict[str, object] = {
        "id": spec.id,
        "label": spec.label,
        "entity": spec.entity,
        "period_id": period_id,
        "unit_scale": best.scale,
        "currency": best.currency,
        "per_share": spec.per_share,
        "is_apm": spec.is_apm,
    }
    if len(agreeing) != len(group):
        pages = tuple(sorted({c.page for c in group}))
        message = f"{period_id}: printed occurrences disagree; no value stated"
        warnings.append(FactWarning(code="conflict", fact=spec.id, pages=pages, message=message))
        return SupplementalFact.model_validate(
            {
                **common,
                "value": None,
                "page": None,
                "raw_text": None,
                "confidence": 0.0,
                "sources": [_source(c).model_dump() for c in group],
                "note": "conflicting printed occurrences",
            }
        )
    bonus = AGREEMENT_BONUS if len({c.page for c in agreeing}) > 1 else 0.0
    return SupplementalFact.model_validate(
        {
            **common,
            "value": float(best.value),
            "page": best.page,
            "raw_text": best.raw,
            "confidence": round(min(MAX_CONFIDENCE, BASE_CONFIDENCE + bonus), 2),
            "sources": [_source(c).model_dump() for c in agreeing],
        }
    )
