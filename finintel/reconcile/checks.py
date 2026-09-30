"""Arithmetic checks (EXTRACTION section 5.2): run only where the rows are printed.

A check never changes a value. It passes or fails within the published-rounding tolerance
`0.5 * n * u` (n figures in the equation, u the unit of the coarsest printed last digit), and its
outcome feeds confidence. A failing check names itself and the difference.

Income-statement chains (revenue -> operating profit -> profit before tax -> net income) sum the
rows between two anchors at the anchor's indent. A row that equals the running total and is styled
as a subtotal is a printed subtotal (Gross profit), not a new amount, and is skipped.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from finintel.mapping.mapper import ItemMapping, section_of
from finintel.tables.models import Column, Row, RowStyle, StatementTable
from finintel.tables.numbers import parse_number


@dataclass(frozen=True)
class CheckResult:
    name: str
    items: tuple[str, ...]  # canonical items whose confidence this check informs
    period_id: str
    passed: bool
    difference: Decimal
    tolerance: Decimal
    detail: str


def period_columns(table: StatementTable) -> dict[str, Column]:
    return {c.period_id: c for c in table.columns if c.usable and c.period_id}


def _cell(row: Row, column: Column) -> tuple[Decimal, int] | None:
    cell = row.cells.get(column.column_id)
    parsed = parse_number(cell.raw_text) if cell else None
    return (parsed.value, parsed.decimals) if parsed else None


def _tolerance(figures: int, decimals: Sequence[int]) -> Decimal:
    unit = Decimal(1).scaleb(-min(decimals)) if decimals else Decimal(1)
    return Decimal("0.5") * figures * unit


def _compare(
    name: str,
    items: tuple[str, ...],
    period: str,
    total: tuple[Decimal, int],
    parts: Sequence[tuple[Decimal, int]],
    detail: str,
) -> CheckResult:
    calc = sum((v for v, _ in parts), Decimal(0))
    tol = _tolerance(len(parts) + 1, [d for _, d in (total, *parts)])
    diff = total[0] - calc
    return CheckResult(name, items, period, abs(diff) <= tol, diff, tol, detail)


def run_checks(table: StatementTable, mapped: Mapping[str, ItemMapping]) -> list[CheckResult]:
    rows = table.rows
    index = {r.row_id: i for i, r in enumerate(rows)}
    results: list[CheckResult] = []
    for period, column in period_columns(table).items():

        def val(item: str, _c: Column = column) -> tuple[Decimal, int] | None:
            m = mapped.get(item)
            return _cell(m.row, _c) if m and m.row else None

        # Section sums: a subtotal equals the figure rows between its section heading and itself.
        for item in (
            "current_assets",
            "current_liabilities",
            "non_current_assets",
            "non_current_liabilities",
        ):
            m, total = mapped.get(item), val(item)
            if not (m and m.row and total):
                continue
            i = index[m.row.row_id]
            _, start = section_of(rows, i)
            parts = [p for r in rows[(start or 0) + 1 : i] if r.cells and (p := _cell(r, column))]
            if parts:
                results.append(
                    _compare(
                        f"{item}_section_sum",
                        (item,),
                        period,
                        total,
                        parts,
                        f"{len(parts)} rows above",
                    )
                )

        ta, nca, ca = val("total_assets"), val("non_current_assets"), val("current_assets")
        if ta and nca and ca:
            results.append(
                _compare(
                    "total_assets_sum",
                    ("total_assets", "non_current_assets", "current_assets"),
                    period,
                    ta,
                    [nca, ca],
                    "non-current + current assets",
                )
            )
        tl, cl, ncl = (
            val("total_liabilities"),
            val("current_liabilities"),
            val("non_current_liabilities"),
        )
        if tl and cl and ncl:
            results.append(
                _compare(
                    "total_liabilities_sum",
                    ("total_liabilities", "current_liabilities"),
                    period,
                    tl,
                    [cl, ncl],
                    "current + non-current liabilities",
                )
            )
        te = val("total_equity")
        if ta and tl and te:
            results.append(
                _compare(
                    "net_assets_identity",
                    ("total_assets", "total_liabilities", "total_equity"),
                    period,
                    te,
                    [(ta[0] - tl[0], 0)],
                    "total assets - total liabilities",
                )
            )
        results += _equity_components(table, mapped, period, column)
        chains: dict[str, tuple[str, str]] = {
            "operating_profit_chain": ("revenue", "operating_profit"),
            "profit_before_tax_chain": ("operating_profit", "profit_before_tax"),
            "net_income_chain": ("profit_before_tax", "net_income"),
        }
        for chain_name, (first_item, last_item) in chains.items():
            if (
                r := _chain(table, mapped, first_item, last_item, period, column, chain_name)
            ) is not None:
                results.append(r)
    return results


def _equity_components(
    table: StatementTable, mapped: Mapping[str, ItemMapping], period: str, column: Column
) -> list[CheckResult]:
    m = mapped.get("total_equity")
    if not (m and m.row):
        return []
    total = _cell(m.row, column)
    rows = table.rows
    i = next(k for k, r in enumerate(rows) if r.row_id == m.row.row_id)
    section, start = section_of(rows, i)
    if not total or section != "equity":
        return []
    parts = [
        p
        for r in rows[(start or 0) + 1 : i]
        if r.cells and not r.label_text.lower().startswith("total") and (p := _cell(r, column))
    ]
    if not parts:
        return []
    return [
        _compare(
            "total_equity_components",
            ("total_equity",),
            period,
            total,
            parts,
            f"{len(parts)} equity rows",
        )
    ]


def _chain(
    table: StatementTable,
    mapped: Mapping[str, ItemMapping],
    start: str,
    end: str,
    period: str,
    column: Column,
    name: str,
) -> CheckResult | None:
    a, b = mapped.get(start), mapped.get(end)
    if not (a and a.row and b and b.row):
        return None
    rows = table.rows
    ia = next(k for k, r in enumerate(rows) if r.row_id == a.row.row_id)
    ib = next(k for k, r in enumerate(rows) if r.row_id == b.row.row_id)
    anchor, target = _cell(a.row, column), _cell(b.row, column)
    if ib <= ia or not anchor or not target:
        return None
    running, parts = anchor[0], []
    for r in rows[ia + 1 : ib]:
        if not r.cells or r.indent_level > a.row.indent_level:
            continue
        cell = _cell(r, column)
        if cell is None:
            continue
        if r.style is not RowStyle.NORMAL and cell[0] == running:
            continue  # a printed subtotal
        running += cell[0]
        parts.append(cell)
    if not parts:
        return None  # nothing printed between the anchors: nothing to check
    return _compare(
        name, (end, start), period, target, [anchor, *parts], f"{start} plus {len(parts)} rows"
    )
