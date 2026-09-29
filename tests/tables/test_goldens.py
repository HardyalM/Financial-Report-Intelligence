"""StatementTables on the labelled goldens (M2.2 gate). PDFs are git-ignored, so CI skips this.

Every labelled cell in fixtures/expected/company_a.json must exist in the table of its statement,
on its labelled page, in a value column, with the same printed text (canonical comparison), for
both text-layer engines. Unilever-specific hazards are pinned too.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

import pytest

from finintel.cache import StageCache
from finintel.cli.common import cached_text_layer
from finintel.ingest import sha256_file
from finintel.locate import StatementType, locate
from finintel.tables import ColumnKind, StatementTable, canonical, statement_tables

ROOT = Path(__file__).resolve().parents[2]
ENGINES = ["pdfplumber", "pymupdf_tables"]


@cache
def _tables(name: str) -> dict[StatementType, dict[str, StatementTable]]:
    pdf = ROOT / "fixtures" / "pdfs" / f"{name}.pdf"
    if not pdf.exists():
        pytest.skip(f"{pdf.name} not in fixtures/pdfs/ (git-ignored; PLAN section 7.1)")
    cache_ = StageCache(ROOT / "artifacts" / "cache")
    sha = sha256_file(pdf)
    layer, _ = cached_text_layer(pdf, sha, cache_)
    return statement_tables(pdf, sha, layer, locate(layer), cache_)


def _labelled() -> list[tuple[str, dict[str, object], dict[str, object]]]:
    path = ROOT / "fixtures" / "expected" / "company_a.json"
    if not path.exists():
        return []
    labels = json.loads(path.read_text(encoding="utf-8"))
    return [
        (item_id, item, value)
        for item_id, item in labels["items"].items()
        for value in item["values"]
        if value.get("raw_text")
    ]


CELLS = _labelled()


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize(
    ("item_id", "item", "value"), CELLS, ids=[f"{i}-{v['period_id']}" for i, _, v in CELLS]
)
def test_every_labelled_cell_is_in_the_table(
    engine: str, item_id: str, item: dict[str, object], value: dict[str, object]
) -> None:
    table = _tables("company_a")[StatementType(str(item["statement"]))][engine]
    value_ids = {c.column_id for c in table.columns if c.kind is ColumnKind.VALUE}
    hits = [
        (row.row_id, column_id)
        for row in table.rows
        for column_id, cell in row.cells.items()
        if cell.page == value["page"]
        and column_id in value_ids
        and canonical(cell.raw_text) == canonical(str(value["raw_text"]))
    ]
    assert hits, f"{item_id} {value['period_id']} {value['raw_text']!r} not on p.{value['page']}"


def test_the_income_statement_ends_where_comprehensive_income_begins() -> None:
    table = _tables("company_a")[StatementType.INCOME_STATEMENT]["pdfplumber"]
    labels = [row.label_text for row in table.rows]
    assert labels.count("Net profit") == 1  # the SOCI's "Net profit" below is not in this table
    assert not any("comprehensive income" in label.lower() for label in labels)


def test_hanging_brackets_and_superscripts() -> None:
    table = _tables("company_a")[StatementType.INCOME_STATEMENT]["pymupdf_tables"]
    rows = {row.label_text: row for row in table.rows}
    finance = rows["Net finance costs"]
    assert [c.raw_text for c in finance.cells.values()] == ["(604)", "(486)", "(493)"]
    [of_which] = [r for r in table.rows if r.label_text.startswith("of which")]
    assert [c.raw_text for c in of_which.cells.values()] == ["(406)", "489", "2,335"]
    assert of_which.indent_level > rows["Operating profit"].indent_level


def test_letter_suffixed_note_references_are_notes() -> None:
    table = _tables("company_a")[StatementType.BALANCE_SHEET]["pdfplumber"]
    refs = {row.note_ref for row in table.rows if row.note_ref}
    assert {"4B", "15C", "17A", "6B"} <= refs
    for row in table.rows:
        assert all(cell.parsed_value is not None for cell in row.cells.values())


def test_lloyds_pence_are_recorded_unparsed() -> None:
    table = _tables("company_b")[StatementType.INCOME_STATEMENT]["pdfplumber"]
    [basic] = [row for row in table.rows if row.label_text == "Basic earnings per share"]
    assert [(c.raw_text, c.parsed_value) for c in basic.cells.values()] == [
        ("6.3p", None), ("7.6p", None), ("4.9p", None),
    ]  # fmt: skip


@pytest.mark.parametrize("name", ["company_a", "company_b"])
def test_the_two_text_layer_engines_agree_on_the_goldens(name: str) -> None:
    for by_engine in _tables(name).values():
        readings = [
            [
                (r.label_text, r.note_ref, {k: c.raw_text for k, c in r.cells.items()})
                for r in t.rows
            ]
            for t in by_engine.values()
        ]
        assert readings[0] == readings[1]
