"""Header semantics (EXTRACTION section 3; SCHEMA sections 7 and 8).

From the print only:
- Unit and currency: exactly one unit token per statement (SCHEMA section 7's table), in its
  column headers or title block. None, or two different ones, blocks the pipeline with
  `needs_unit_confirmation`. The income statement and balance sheet must agree. A bare "$" is USD
  only if the report states a US dollar presentation currency; otherwise `currency_ambiguous`,
  which also blocks. Nothing is defaulted.
- Periods: column -> period from printed dates, never from position. The day and month come from
  the column header or the title block ("for the year ended 31 December"); the year from the
  column. A "year ended" phrase dates every year column of the statement; a "52 weeks ended" or
  "period ended" phrase dates only the column with its own year, because comparative weeks shift.
- Restatement: "Restated" on a column, or a footnote marker on its year when the page says
  "restated". The restated column is used (it is the current basis) and flagged.
- Columnar income statements: when a period has several columns, only the one headed "Total" or
  "Statutory" is used; otherwise that period is ambiguous and its figures stay null.
- Entity columns: when Group and Company columns sit side by side, only Group columns are used.

Headers spanning a group of columns (a year centred over three) apply to every column in the group.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from pydantic import BaseModel, ConfigDict

from finintel.locate.models import StatementType
from finintel.locate.scope import is_entity_label, scope_of_text
from finintel.locate.signals import normalise
from finintel.parse.text_layer import TextLayer
from finintel.tables.models import Column, ColumnKind, HeaderWord, StatementTable

MONTHS = {
    m: i
    for i, names in enumerate(
        [("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"), ("may",),
         ("june", "jun"), ("july", "jul"), ("august", "aug"), ("september", "sep", "sept"),
         ("october", "oct"), ("november", "nov"), ("december", "dec")],
        start=1,
    )
    for m in names
}  # fmt: skip
_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
_FULL_DATE = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH})\.?\s+((?:19|20)\d{{2}})\b")
_FISCAL = re.compile(r"\b((?:19|20)\d{2})\s*[/\u2013-]\s*(\d{2})\b")
_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_PERIOD_PHRASE = re.compile(
    rf"\b(?:(?P<weeks>\d{{2}}|fifty-two|fifty-three)\s+weeks?|(?P<kind>financial\s+year|year|period))"
    rf"\s+(?:ended|ending|to)\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month>{_MONTH})\.?"
    rf"(?:\s+(?P<year>(?:19|20)\d{{2}}))?"
)
_AT_PHRASE = re.compile(
    rf"\b(?:as\s+)?at\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month>{_MONTH})\.?"
    rf"(?:\s+(?P<year>(?:19|20)\d{{2}}))?"
)
_RESTATED = re.compile(r"\brestated\b")
_MARKER = re.compile(r"^(?:19|20)\d{2}(?:[*\u2020\u2021\u00b9\u00b2\u00b3]|\([a-z0-9]\))$")
_TOTAL = re.compile(r"\b(?:total|statutory)\b")
_WORDS_WEEKS = {"fifty-two": 52, "fifty-three": 53}
PHRASE_GAP = 4.0  # pt: header words closer than this form one printed phrase

# SCHEMA section 7. Order matters: the most specific token wins at each position.
_UNITS: tuple[tuple[str, str | None, int], ...] = (
    (r"us\$\s?(?:m|mn|millions?)\b", "USD", 1_000_000),
    (r"us\$\s?'?000\b|us\$\s?thousands?\b", "USD", 1_000),
    (r"usd\s?(?:m|mn|millions?)\b", "USD", 1_000_000),
    (r"£\s?(?:m|mn|millions?)\b", "GBP", 1_000_000),
    (r"£\s?'?000\b|£\s?(?:k|thousands?)\b", "GBP", 1_000),
    (r"€\s?(?:m|mn|millions?)\b|\beur\s?m\b", "EUR", 1_000_000),
    (r"€\s?'?000\b|€\s?thousands?\b", "EUR", 1_000),
    (r"\$\s?(?:m|mn|millions?)\b", None, 1_000_000),  # "$" alone: currency to be established
    (r"\$\s?'?000\b|\$\s?thousands?\b", None, 1_000),
    (r"£(?!\s?(?:\d|m\b|mn\b|million|'?000|k\b|thousand))", "GBP", 1),
)
_UNIT_RE = re.compile("|".join(f"(?P<u{i}>{p})" for i, (p, _, _) in enumerate(_UNITS)))
_PRESENTATION = re.compile(
    r"presentation currency (?:of the group )?is (?:the )?(us dollars?|united states dollars?|"
    r"pounds? sterling|sterling|euros?)|presented in (us dollars|united states dollars|"
    r"pounds sterling|sterling|euros)"
)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class HeaderWarning(_Frozen):
    code: str
    message: str
    page: int | None = None
    statement: StatementType | None = None


class UnitDecision(_Frozen):
    statement_type: StatementType
    status: str  # "ok", "needs_unit_confirmation" or "currency_ambiguous"
    currency: str | None
    unit_scale: int | None
    tokens: tuple[str, ...]  # distinct unit tokens as printed
    evidence: str


class Period(_Frozen):
    id: str
    label: str
    end_date: str | None
    is_restated: bool = False
    weeks: int | None = None


class HeaderResult(_Frozen):
    status: str  # "ok", "needs_unit_confirmation" or "currency_ambiguous"
    currency: str | None
    unit_scale: int | None
    periods: tuple[Period, ...]
    units: tuple[UnitDecision, ...]
    tables: dict[StatementType, StatementTable]
    warnings: tuple[HeaderWarning, ...]


# ------------------------------------------------------------------------------ entry point


def read_headers(tables: Mapping[StatementType, StatementTable], layer: TextLayer) -> HeaderResult:
    """Header semantics for one engine's tables (one table per located statement)."""
    warnings: list[HeaderWarning] = []
    presentation = presentation_currency(layer)
    units = [decide_unit(t, presentation) for t in tables.values()]
    updated: dict[StatementType, StatementTable] = {}
    periods: dict[str, Period] = {}
    for kind, table in tables.items():
        new_table, table_periods, notes = assign_periods(table, layer)
        updated[kind] = new_table
        warnings.extend(notes)
        for period in table_periods:
            known = periods.get(period.id)
            if known and known.end_date and period.end_date and known.end_date != period.end_date:
                warnings.append(
                    HeaderWarning(
                        code="period_ambiguous",
                        message=f"{period.id} ends {known.end_date} on one statement and "
                        f"{period.end_date} on the {kind.value.replace('_', ' ')}",
                        statement=kind,
                    )
                )
            periods[period.id] = _merge(known, period)

    status, currency, scale, unit_warnings = _pack_unit(units)
    warnings = unit_warnings + warnings
    ordered = sorted(periods.values(), key=lambda p: (p.end_date or p.id[2:], p.id), reverse=True)
    return HeaderResult(
        status=status,
        currency=currency,
        unit_scale=scale,
        periods=tuple(ordered),
        units=tuple(units),
        tables=updated,
        warnings=tuple(warnings),
    )


# ------------------------------------------------------------------------------ units


def presentation_currency(layer: TextLayer) -> tuple[str, int] | None:
    """(ISO code, page) from a narrative statement of presentation currency, if printed."""
    codes = {"us dollar": "USD", "united states dollar": "USD", "sterling": "GBP", "euro": "EUR"}
    for page in layer.pages:
        match = _PRESENTATION.search(normalise(page.text))
        if match:
            named = next(g for g in match.groups() if g)
            code = next(v for k, v in codes.items() if k in named)
            return code, page.page
    return None


def decide_unit(table: StatementTable, presentation: tuple[str, int] | None) -> UnitDecision:
    page = table.pages[0] if table.pages else None
    where = f"{table.statement_type.value.replace('_', ' ')} (p.{page})"
    found: dict[tuple[str | None, int], str] = {}
    for text in [*_header_lines(table.header_words), *table.title_block]:
        for match in _UNIT_RE.finditer(normalise(text)):
            index = int(next(k for k, v in match.groupdict().items() if v)[1:])
            _, currency, scale = _UNITS[index]
            found.setdefault((currency, scale), match.group(0))
    tokens = tuple(found.values())
    if not found:
        return UnitDecision(
            statement_type=table.statement_type,
            status="needs_unit_confirmation",
            currency=None,
            unit_scale=None,
            tokens=(),
            evidence=f"no unit token in the column headers or title of the {where}",
        )
    if len(found) > 1:
        return UnitDecision(
            statement_type=table.statement_type,
            status="needs_unit_confirmation",
            currency=None,
            unit_scale=None,
            tokens=tokens,
            evidence=f"conflicting unit tokens {list(tokens)} on the {where}",
        )
    (currency, scale), token = next(iter(found.items()))
    if currency is None:
        if presentation is not None and presentation[0] == "USD":
            return UnitDecision(
                statement_type=table.statement_type,
                status="ok",
                currency="USD",
                unit_scale=scale,
                tokens=tokens,
                evidence=f'"{token}" on the {where}; US dollar presentation currency stated on '
                f"p.{presentation[1]}",
            )
        return UnitDecision(
            statement_type=table.statement_type,
            status="currency_ambiguous",
            currency=None,
            unit_scale=scale,
            tokens=tokens,
            evidence=f'"{token}" on the {where} names no currency, and the report does not state '
            "a US dollar presentation currency",
        )
    return UnitDecision(
        statement_type=table.statement_type,
        status="ok",
        currency=currency,
        unit_scale=scale,
        tokens=tokens,
        evidence=f'"{token}" on the {where}',
    )


def _pack_unit(
    units: Sequence[UnitDecision],
) -> tuple[str, str | None, int | None, list[HeaderWarning]]:
    warnings: list[HeaderWarning] = []
    for unit in units:
        if unit.status != "ok":
            code = "currency_ambiguous" if unit.status == "currency_ambiguous" else "unit_ambiguous"
            warnings.append(
                HeaderWarning(code=code, message=unit.evidence, statement=unit.statement_type)
            )
    if warnings:
        status = (
            "needs_unit_confirmation"
            if any(w.code == "unit_ambiguous" for w in warnings)
            else "currency_ambiguous"
        )
        return status, None, None, warnings
    if not units:
        return (
            "needs_unit_confirmation",
            None,
            None,
            [
                HeaderWarning(
                    code="unit_ambiguous", message="no statement located to read a unit from"
                )
            ],
        )
    distinct = {(u.currency, u.unit_scale) for u in units}
    if len(distinct) > 1:
        detail = "; ".join(u.evidence for u in units)
        return (
            "needs_unit_confirmation",
            None,
            None,
            [
                HeaderWarning(
                    code="unit_ambiguous", message=f"the statements disagree on the unit: {detail}"
                )
            ],
        )
    currency, scale = distinct.pop()
    return "ok", currency, scale, []


def _header_lines(words: Sequence[HeaderWord]) -> list[str]:
    rows: dict[int, list[HeaderWord]] = defaultdict(list)
    for word in words:
        rows[word.row].append(word)
    return [
        " ".join(w.text for w in sorted(r, key=lambda w: w.bbox[0]))
        for _, r in sorted(rows.items())
    ]


# ------------------------------------------------------------------------------ periods


@dataclass
class _Phrase:
    row: int
    text: str
    x0: float
    x1: float

    @property
    def centre(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class _ColumnHeader:
    column: Column
    phrases: list[_Phrase] = field(default_factory=list)

    def text(self) -> str:
        return " ".join(p.text for p in sorted(self.phrases, key=lambda p: (p.row, p.x0)))


def assign_periods(
    table: StatementTable, layer: TextLayer
) -> tuple[StatementTable, list[Period], list[HeaderWarning]]:
    kind = table.statement_type
    page = table.pages[0] if table.pages else None
    values = [c for c in table.columns if c.kind is ColumnKind.VALUE]
    headers = {c.column_id: _ColumnHeader(c) for c in values}
    if values:
        left = min(c.x0 for c in values) - 3
        rows: dict[int, list[_Phrase]] = defaultdict(list)
        for phrase in _phrases(table.header_words):
            if phrase.x1 > left:  # "Notes" and the label area are not column headers
                rows[phrase.row].append(phrase)
        for row in rows.values():
            for phrase in row:
                for column_id in _columns_for(phrase, values, row):
                    headers[column_id].phrases.append(phrase)

    title = normalise(" ".join(table.title_block))
    title_phrase = _PERIOD_PHRASE.search(title) or _AT_PHRASE.search(title)
    page_text = normalise(layer.page(page).text) if page else ""
    warnings: list[HeaderWarning] = []
    updated: dict[str, Column] = {}
    for column_id, header in headers.items():
        updated[column_id] = _period_column(header, title_phrase, page_text)

    _entity_columns(updated, {cid: h.text() for cid, h in headers.items()}, kind, page, warnings)
    _one_column_per_period(updated, kind, page, warnings)
    for column in updated.values():
        if column.excluded is None and column.period_id is None:
            warnings.append(
                HeaderWarning(
                    code="period_ambiguous",
                    message=f'column "{column.header_text}" on the {kind.value.replace("_", " ")} '
                    f"(p.{page}) carries no period; its figures stay null",
                    page=page,
                    statement=kind,
                )
            )
            updated[column.column_id] = column.model_copy(
                update={"excluded": "no period in the column header"}
            )

    for column in updated.values():
        if column.usable and column.is_restated:
            warnings.append(
                HeaderWarning(
                    code="restated_comparative",
                    message=f"{column.period_id} on the {kind.value.replace('_', ' ')} "
                    f"(p.{page}) is restated; the restated figures are used as the current basis",
                    page=page,
                    statement=kind,
                )
            )
    columns = tuple(updated.get(c.column_id, c) for c in table.columns)
    periods = [
        Period(
            id=c.period_id,
            label=c.period_label or c.period_id,
            end_date=c.end_date,
            is_restated=c.is_restated,
            weeks=c.weeks,
        )
        for c in columns
        if c.usable and c.period_id is not None
    ]
    return table.model_copy(update={"columns": columns}), periods, warnings


def _period_column(header: _ColumnHeader, phrase: re.Match[str] | None, page_text: str) -> Column:
    column = header.column
    text = header.text()
    norm = normalise(text)
    label: str | None = None
    end: date | None = None
    year: int | None = None
    basis = ""
    if full := _FULL_DATE.search(norm):
        day, month, yr = int(full.group(1)), MONTHS[full.group(2)], int(full.group(3))
        end, year, label, basis = _date(yr, month, day), yr, full.group(0), "printed in the column"
    elif fiscal := _FISCAL.search(norm):
        start = int(fiscal.group(1))
        year, label = start - start % 100 + int(fiscal.group(2)), fiscal.group(0)
        if year < start:
            year += 100
    elif plain := _YEAR.search(norm):
        year, label = int(plain.group(1)), plain.group(1)
    weeks: int | None = None
    if end is None and year is not None and phrase is not None:
        day, month = int(phrase.group("day")), MONTHS[phrase.group("month")]
        groups = phrase.groupdict()
        phrase_year = int(groups["year"]) if groups.get("year") else None
        if phrase_year is None or phrase_year == year:
            end, basis = _date(year, month, day), f'"{phrase.group(0)}" in the title'
            weeks = _weeks(phrase) if phrase_year == year else None
        elif (groups.get("kind") or "").endswith("year") and not groups.get("weeks"):
            # A "year ended" phrase dates the comparative years too: years are consecutive.
            # Weeks-based, "period" and "as at" phrases do not: 52/53-week ends shift by days.
            end, basis = _date(year, month, day), f'"{phrase.group(0)}": years end on the same day'
    restated = bool(_RESTATED.search(norm)) or (
        any(_MARKER.match(p.text) for p in header.phrases) and bool(_RESTATED.search(page_text))
    )
    return column.model_copy(
        update={
            "period_id": f"FY{end.year if end else year}" if (end or year) else None,
            "period_label": label,
            "end_date": end.isoformat() if end else None,
            "is_restated": restated,
            "is_total_column": bool(_TOTAL.search(norm)),
            "weeks": weeks,
            "evidence": f"{column.evidence}; period from {basis or 'the printed year'}"
            if year
            else column.evidence,
        }
    )


def _entity_columns(
    columns: dict[str, Column],
    header_texts: Mapping[str, str],
    kind: StatementType,
    page: int | None,
    warnings: list[HeaderWarning],
) -> None:
    """Only Group columns feed values when Group and Company columns sit side by side."""
    entities = {cid: _entity(header_texts.get(cid, "")) for cid in columns}
    if not any(entities.values()):
        return
    if "group" not in entities.values():
        warnings.append(
            HeaderWarning(
                code="entity_scope_ambiguous",
                message=f"entity columns on the {kind.value.replace('_', ' ')} (p.{page}) name no "
                "group; figures stay null",
                page=page,
                statement=kind,
            )
        )
    for cid, entity in entities.items():
        update: dict[str, object] = {"entity": entity}
        if entity != "group":
            update["excluded"] = f"{entity or 'unnamed'} column: only group figures are used in v1"
        columns[cid] = columns[cid].model_copy(update=update)


def _entity(header: str) -> str | None:
    for word in normalise(header).split():
        if is_entity_label(word):
            scope = scope_of_text(word)
            return "group" if scope and scope.value == "group" else "company"
    return None


def _one_column_per_period(
    columns: dict[str, Column], kind: StatementType, page: int | None, warnings: list[HeaderWarning]
) -> None:
    by_period: dict[str, list[str]] = defaultdict(list)
    for cid, column in columns.items():
        if column.excluded is None and column.period_id:
            by_period[column.period_id].append(cid)
    for period, ids in by_period.items():
        if len(ids) < 2:
            continue
        totals = [cid for cid in ids if columns[cid].is_total_column]
        if len(totals) == 1:
            for cid in ids:
                if cid != totals[0]:
                    columns[cid] = columns[cid].model_copy(
                        update={"excluded": f'component column "{columns[cid].header_text}": '
                                "only the statutory total is used"}
                    )  # fmt: skip
            continue
        headers = [columns[cid].header_text for cid in ids]
        warnings.append(
            HeaderWarning(
                code="period_ambiguous",
                message=f"{len(ids)} columns for {period} on the {kind.value.replace('_', ' ')} "
                f"(p.{page}) and no single Total or Statutory column: {headers}; figures stay null",
                page=page,
                statement=kind,
            )
        )
        for cid in ids:
            columns[cid] = columns[cid].model_copy(
                update={"excluded": f"{period} has several columns"}
            )


def _phrases(words: Sequence[HeaderWord]) -> list[_Phrase]:
    phrases: list[_Phrase] = []
    for word in sorted(words, key=lambda w: (w.row, w.bbox[0])):
        last = phrases[-1] if phrases else None
        if last and last.row == word.row and word.bbox[0] - last.x1 <= PHRASE_GAP:
            last.text, last.x1 = f"{last.text} {word.text}", max(last.x1, word.bbox[2])
        else:
            phrases.append(_Phrase(word.row, word.text, word.bbox[0], word.bbox[2]))
    return phrases


def _columns_for(phrase: _Phrase, values: Sequence[Column], row: Sequence[_Phrase]) -> list[str]:
    """Columns a header phrase applies to.

    In a full row (a phrase per column) a phrase applies to the columns it overlaps. In a sparse
    row, a phrase right-aligned with one column is that column's own ("Restated"); any other
    phrase spans a group (a year centred over three columns) and applies to every column nearer
    to it than to any other phrase in the row."""
    overlapping = [
        c.column_id for c in values if min(phrase.x1, c.x1 + 3) - max(phrase.x0, c.x0 - 3) > 0
    ]
    if len(row) >= len(values):
        return overlapping
    aligned = [
        c.column_id for c in values if c.column_id in overlapping and abs(phrase.x1 - c.x1) <= 3
    ]
    if len(overlapping) == 1 and aligned:
        return aligned
    spanning = [p for p in row if not _aligned_to_one(p, values)]
    near = []
    for column in values:
        centre = (column.x0 + column.x1) / 2
        if spanning and min(spanning, key=lambda p: abs(p.centre - centre)) is phrase:
            near.append(column.column_id)
    return near


def _aligned_to_one(phrase: _Phrase, values: Sequence[Column]) -> bool:
    hits = [c for c in values if min(phrase.x1, c.x1 + 3) - max(phrase.x0, c.x0 - 3) > 0]
    # Figure columns and their headers are right-aligned; a centred header only looks aligned.
    return len(hits) == 1 and abs(phrase.x1 - hits[0].x1) <= 3


def _merge(known: Period | None, new: Period) -> Period:
    if known is None:
        return new
    return known.model_copy(
        update={
            "end_date": known.end_date or new.end_date,
            "is_restated": known.is_restated or new.is_restated,
            "weeks": known.weeks or new.weeks,
        }
    )


def _weeks(phrase: re.Match[str] | None) -> int | None:
    if phrase is None or not phrase.groupdict().get("weeks"):
        return None
    text = phrase.group("weeks")
    return _WORDS_WEEKS.get(text) or int(text)


def _date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None
