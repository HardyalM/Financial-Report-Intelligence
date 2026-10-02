"""Deterministic row mapping (EXTRACTION section 4.3).

Applied in order; the first rule that yields a unique candidate wins:
1. exact alias, in the right section context  (method `exact_alias`)
2. regex alias                                 (`regex_alias`)
3. structural: an unlabelled subtotal or total row that closes a named section  (`structural`)
The exclusion filter removes a row whatever rule produced it. Two candidates at one precedence: the
total-styled row wins if it is unique; rows that print the same text in every column are the same
figure printed twice (a bank repeats "Profit for the year" under its attribution lines), so the
first is taken; otherwise the item is `alias_weak` and stays null.
No number is interpreted here: repeated rows are compared as printed text, never by magnitude.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from finintel.mapping.aliases import AliasSpec, normalise_label
from finintel.tables.models import Row, RowStyle, StatementTable

METHOD_BASE = {"exact_alias": 0.95, "regex_alias": 0.90, "structural": 0.85}
_COLON_HEADER = re.compile(r":\s*$")


@dataclass(frozen=True)
class ItemMapping:
    item: str
    method: str | None  # exact_alias, regex_alias, structural; None when nothing unique
    row: Row | None
    rivals: tuple[Row, ...] = ()  # the tied rows when alias_weak
    weak: bool = False


def section_of(rows: Sequence[Row], index: int) -> tuple[str | None, int | None]:
    """(normalised heading, its row index): the nearest preceding heading row that does not end in
    a colon. Colon headings ("Pensions and post-retirement healthcare liabilities:") open a
    sub-list inside their section and never replace it."""
    for j in range(index - 1, -1, -1):
        row = rows[j]
        if not row.cells and row.label_text and not _COLON_HEADER.search(row.label_text):
            return normalise_label(row.label_text), j
    return None, None


def _excluded(label: str, spec: AliasSpec) -> bool:
    return any(token in label for token in spec.exclude_any)


def _printed(row: Row) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((k, c.raw_text) for k, c in row.cells.items()))


def _unique(candidates: list[Row]) -> tuple[Row | None, tuple[Row, ...]]:
    if len(candidates) == 1:
        return candidates[0], ()
    totals = [r for r in candidates if r.style is RowStyle.TOTAL]
    if len(totals) == 1:
        return totals[0], ()
    first = _printed(candidates[0])
    if first and all(_printed(r) == first for r in candidates[1:]):
        return candidates[0], ()  # one figure printed twice, not a choice between figures
    return None, tuple(candidates)


def map_item(table: StatementTable, spec: AliasSpec) -> ItemMapping:
    if table.statement_type is not spec.statement:
        return ItemMapping(spec.item, None, None)
    rows = table.rows
    figure_rows = [(i, r) for i, r in enumerate(rows) if r.cells]

    def in_section(i: int) -> bool:
        if spec.sections is None:
            return True
        section, _ = section_of(rows, i)
        return section in spec.sections

    stages: list[tuple[str, list[Row]]] = [
        (
            "exact_alias",
            [
                r
                for i, r in figure_rows
                if normalise_label(r.label_text) in spec.include_exact and in_section(i)
            ],
        ),
        (
            "regex_alias",
            [
                r
                for i, r in figure_rows
                if any(p.match(normalise_label(r.label_text)) for p in spec.include_regex)
                and in_section(i)
            ],
        ),
        (
            "structural",
            [
                r
                for i, r in figure_rows
                if spec.structural
                and not normalise_label(r.label_text)
                and r.style in (RowStyle.SUBTOTAL, RowStyle.TOTAL)
                and section_of(rows, i)[0] in spec.structural
            ],
        ),
    ]
    for method, found in stages:
        found = [r for r in found if not _excluded(normalise_label(r.label_text), spec)]
        if not found:
            continue
        row, rivals = _unique(found)
        if row is not None:
            return ItemMapping(spec.item, method, row)
        return ItemMapping(spec.item, None, None, rivals=rivals, weak=True)
    return ItemMapping(spec.item, None, None)


def map_table(table: StatementTable, specs: Mapping[str, AliasSpec]) -> dict[str, ItemMapping]:
    return {
        item: m
        for item, spec in specs.items()
        if spec.statement is table.statement_type and (m := map_item(table, spec))
    }
