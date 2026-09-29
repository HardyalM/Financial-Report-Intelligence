"""Synthetic layout specs (ADR-010, EVAL section 3.7).

A spec describes a small report page by page and states what the pipeline must conclude about it.
The spec is the only source of truth: every printed figure exists because the spec prints it.

Every numeric value is reviewed by the tech lead before commit. To make that review about meaning
rather than arithmetic, `load_spec` refuses a spec whose printed subtotals do not add up
(`sum_of`), so a reviewer never has to re-add a column.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

SPECS_DIR = Path(__file__).parent / "specs"
_NIL = {"-", "\u2013", "\u2014", "nil"}


class SpecError(ValueError):
    """The spec is inconsistent; it must be fixed before it can be truth."""


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Row(_Model):
    label: str = ""
    id: str | None = None  # needed when a label repeats (e.g. current and non-current borrowings)
    note: str = ""
    values: tuple[str, ...] = ()  # printed exactly as the PDF shows them, one per period
    style: Literal["normal", "section", "subtotal", "total"] = "normal"
    sum_of: tuple[str, ...] = ()  # ids or labels whose printed values this row must equal

    @property
    def key(self) -> str:
        return self.id or self.label


class StatementPage(_Model):
    kind: Literal["statement"]
    statement: str
    title: str | None = None  # None: a continuation page without a title
    header: str | None = None  # section header printed above the title
    subtitle: str | None = None
    entity_columns: tuple[str, ...] = ()
    continuation: bool = False  # rows continue the previous statement page
    rows: tuple[Row, ...]


class NarrativePage(_Model):
    kind: Literal["narrative"]
    title: str
    header: str | None = None
    paragraphs: int = 3


Page = Annotated[StatementPage | NarrativePage, Field(discriminator="kind")]


class StatementExpectation(_Model):
    pages: tuple[int, ...]
    scope: str


class Rejection(_Model):
    page: int
    statement: str
    scope: str


class Expectation(_Model):
    statements: dict[str, StatementExpectation]
    rejected: tuple[Rejection, ...] = ()
    document_type: str
    balance_sheet_classified: bool | None
    #: The folio offset the locator must infer, or None when the report is too short to support
    #: one (the locator needs five agreeing pages; see finintel.locate.folios).
    folio_offset: int | None = None


class Spec(_Model):
    name: str
    hazard: str
    description: str
    company: str = "Example Group plc"
    unit: str = "£m"
    periods: tuple[str, ...] = ("2025", "2024")
    chrome: tuple[str, ...] = ()  # navigation bar printed on every page
    folio_offset: int = 0  # printed folio = PDF page - folio_offset
    pages: tuple[Page, ...]
    expect: Expectation


def parse_printed(text: str) -> Decimal:
    """Printed figure to a signed Decimal: brackets are negative, a dash is nil."""
    raw = text.strip()
    if raw.lower() in _NIL:
        return Decimal(0)
    negative = raw.startswith("(") and raw.endswith(")")
    digits = raw.strip("()").replace(",", "").replace("\u2212", "-")
    value = Decimal(digits)
    return -value if negative else value


def statement_groups(spec: Spec) -> Iterator[tuple[int, list[StatementPage]]]:
    """(first PDF page, pages) for each statement and its continuation pages."""
    group: list[StatementPage] = []
    start = 0
    for number, page in enumerate(spec.pages, start=1):
        if isinstance(page, StatementPage) and page.continuation and group:
            group.append(page)
            continue
        if group:
            yield start, group
        group, start = ([page], number) if isinstance(page, StatementPage) else ([], 0)
    if group:
        yield start, group


def check_spec(spec: Spec) -> None:
    periods = len(spec.periods)
    for start, pages in statement_groups(spec):
        rows = [row for page in pages for row in page.rows]
        by_key: dict[str, Row] = {}
        for row in rows:
            if row.style != "section" and len(row.values) != periods:
                raise SpecError(
                    f"p.{start} {row.key!r}: {len(row.values)} values for {periods} periods"
                )
            if row.values and row.key in by_key:
                raise SpecError(f"p.{start} {row.key!r} repeats; give it an id")
            if row.values:
                by_key[row.key] = row
        for row in rows:
            _check_sum(start, row, by_key, periods)
    _check_expectations(spec)


def _check_sum(start: int, row: Row, by_key: dict[str, Row], periods: int) -> None:
    if not row.sum_of:
        return
    missing = [key for key in row.sum_of if key not in by_key]
    if missing:
        raise SpecError(f"p.{start} {row.key!r} sums unknown rows {missing}")
    for i in range(periods):
        total = sum((parse_printed(by_key[k].values[i]) for k in row.sum_of), Decimal(0))
        printed = parse_printed(row.values[i])
        if total != printed:
            raise SpecError(
                f"p.{start} {row.key!r} period {i + 1}: prints {row.values[i]} but its "
                f"components sum to {total}"
            )


def _check_expectations(spec: Spec) -> None:
    pages = spec.pages
    for kind, expected in spec.expect.statements.items():
        for number in expected.pages:
            page = pages[number - 1] if 1 <= number <= len(pages) else None
            if not isinstance(page, StatementPage) or page.statement != kind:
                raise SpecError(f"expect.{kind}: p.{number} is not a {kind} page")
    for rejection in spec.expect.rejected:
        page = pages[rejection.page - 1] if 1 <= rejection.page <= len(pages) else None
        if not isinstance(page, StatementPage) or page.statement != rejection.statement:
            raise SpecError(
                f"expect.rejected: p.{rejection.page} is not a {rejection.statement} page"
            )


def load_spec(path: Path) -> Spec:
    spec = Spec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    check_spec(spec)
    return spec


def all_specs(directory: Path = SPECS_DIR) -> Sequence[Path]:
    return sorted(directory.glob("*.yaml"))
