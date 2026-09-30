"""StatementTables on the synthetic suite: truth is the spec (ADR-010).

For every spec, statement and text-layer engine: every row with figures appears with the printed
label, note reference and figures exactly as the spec prints them, in order; the note column is
never a value column; and value columns carry the period header they sit under.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from evals.synthetic.render import render
from evals.synthetic.spec import Spec, all_specs, load_spec, page_columns, statement_groups
from finintel.locate import StatementType, locate
from finintel.parse.engines.pdfplumber_engine import PdfplumberEngine
from finintel.parse.engines.pymupdf_tables_engine import PymupdfTablesEngine
from finintel.parse.text_layer import TextLayer, read_text_layer
from finintel.tables import ColumnKind, RowStyle, StatementTable, build_statement_table
from finintel.tables.regions import statement_regions

SPECS = all_specs()
ENGINES: list[PdfplumberEngine | PymupdfTablesEngine] = [PdfplumberEngine(), PymupdfTablesEngine()]
KINDS = [StatementType.INCOME_STATEMENT, StatementType.BALANCE_SHEET]


@pytest.fixture(scope="module", params=SPECS, ids=[p.stem for p in SPECS])
def rendered(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> tuple[Spec, Path, TextLayer]:
    spec = load_spec(request.param)
    pdf = render(spec, tmp_path_factory.mktemp("specs") / f"{spec.name}.pdf")
    return spec, pdf, read_text_layer(pdf)


@pytest.fixture(scope="module")
def named(
    tmp_path_factory: pytest.TempPathFactory,
) -> Callable[[str], tuple[Spec, Path, TextLayer]]:
    """Render one spec by name, once per module (for tests about a single hazard)."""
    done: dict[str, tuple[Spec, Path, TextLayer]] = {}

    def get(name: str) -> tuple[Spec, Path, TextLayer]:
        if name not in done:
            spec = load_spec(next(p for p in SPECS if p.stem == name))
            pdf = render(spec, tmp_path_factory.mktemp(name) / f"{name}.pdf")
            done[name] = (spec, pdf, read_text_layer(pdf))
        return done[name]

    return get


def _table(
    rendered: tuple[Spec, Path, TextLayer], kind: StatementType, engine_index: int
) -> StatementTable:
    _, pdf, layer = rendered
    location = locate(layer).statements[kind]
    assert location.status == "found"
    clips = {region.page: [region.bbox] for region in statement_regions(layer, location)}
    parsed = ENGINES[engine_index].parse(pdf, sorted(clips), clips)
    return build_statement_table(layer, location, parsed)


def _expected(
    spec: Spec, kind: StatementType, first_page: int
) -> list[tuple[str, str | None, tuple[str, ...]]]:
    [pages] = [
        p
        for start, p in statement_groups(spec)
        if p[0].statement == kind.value and start == first_page
    ]
    return [
        (row.label, row.note or None, row.values)
        for page in pages
        for row in page.rows
        if row.values
    ]


@pytest.mark.parametrize("engine_index", [0, 1], ids=[e.name for e in ENGINES])
@pytest.mark.parametrize("kind", KINDS, ids=[k.value for k in KINDS])
def test_rows_match_the_spec_exactly(
    rendered: tuple[Spec, Path, TextLayer], kind: StatementType, engine_index: int
) -> None:
    spec = rendered[0]
    table = _table(rendered, kind, engine_index)
    got = [
        (row.label_text, row.note_ref, tuple(cell.raw_text for cell in row.cells.values()))
        for row in table.rows
        if row.cells
    ]
    assert got == _expected(spec, kind, table.pages[0])


@pytest.mark.parametrize("engine_index", [0, 1], ids=[e.name for e in ENGINES])
@pytest.mark.parametrize("kind", KINDS, ids=[k.value for k in KINDS])
def test_no_value_column_is_a_notes_column(
    rendered: tuple[Spec, Path, TextLayer], kind: StatementType, engine_index: int
) -> None:
    spec = rendered[0]
    table = _table(rendered, kind, engine_index)
    [pages] = [
        p for s, p in statement_groups(spec) if p[0].statement == kind.value and s == table.pages[0]
    ]
    columns = page_columns(spec, pages[0])
    values = table.value_columns
    assert len(values) == len(columns)
    for column in values:
        assert "note" not in column.header_text.lower()
    notes = [c for c in table.columns if c.kind is ColumnKind.NOTE]
    printed = pages[0].notes_header or any(row.note for page in pages for row in page.rows)
    if printed:  # a printed "Notes" header or reference: exactly one note column, left of values
        assert len(notes) == 1 and notes[0].x1 < values[0].x0
    else:
        assert notes == []


def test_unheaded_note_column_is_found_by_its_references(
    named: Callable[[str], tuple[Spec, Path, TextLayer]],
) -> None:
    rendered = named("notes_column")
    table = _table(rendered, StatementType.BALANCE_SHEET, 0)
    [note] = [c for c in table.columns if c.kind is ColumnKind.NOTE]
    assert note.header_text == "" and "note references" in note.evidence


def test_sections_and_styles(named: Callable[[str], tuple[Spec, Path, TextLayer]]) -> None:
    rendered = named("company_before_group")
    table = _table(rendered, StatementType.BALANCE_SHEET, 0)
    by_label = {row.label_text: row for row in table.rows if row.label_text}
    assert by_label["Current assets"].style is RowStyle.HEADER
    assert by_label["Inventories"].section_header == "Current assets"
    assert by_label["Total assets"].style is RowStyle.TOTAL
    unlabelled = [row for row in table.rows if not row.label_text]
    assert [row.section_header for row in unlabelled] == [
        "Non-current assets", "Current assets", "Current liabilities", "Non-current liabilities",
    ]  # fmt: skip
    assert all(row.style in (RowStyle.SUBTOTAL, RowStyle.TOTAL) for row in unlabelled)


def test_two_page_statement_keeps_each_rows_page(
    named: Callable[[str], tuple[Spec, Path, TextLayer]],
) -> None:
    rendered = named("two_page_balance_sheet")
    table = _table(rendered, StatementType.BALANCE_SHEET, 0)
    assert table.pages == (3, 4)
    pages = {row.label_text: row.page for row in table.rows if row.label_text}
    assert pages["Total assets"] == 3 and pages["Total equity"] == 4
    carried = next(r for r in table.rows if r.page == 4)
    assert carried.label_text == "Current liabilities"  # the heading opens page 4's section
    assert any("merged pages [3, 4]" in note for note in table.notes)


def test_spread_halves_are_read_separately(
    named: Callable[[str], tuple[Spec, Path, TextLayer]],
) -> None:
    rendered = named("spread_page")
    income = _table(rendered, StatementType.INCOME_STATEMENT, 0)
    balance = _table(rendered, StatementType.BALANCE_SHEET, 0)
    assert {r.label_text for r in income.rows} & {r.label_text for r in balance.rows} == set()
    assert max(c.x1 for c in income.columns) < 595 < min(c.x0 for c in balance.columns)
