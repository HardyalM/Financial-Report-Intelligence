"""Header semantics on the synthetic suite (M2.3 gate): unit, currency, periods, restatement,
the statutory column and entity columns, exactly as each spec's `expect` block says."""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.synthetic.render import render
from evals.synthetic.spec import all_specs, load_spec
from finintel.locate import StatementType, locate
from finintel.parse.engines.pdfplumber_engine import PdfplumberEngine
from finintel.parse.engines.pymupdf_tables_engine import PymupdfTablesEngine
from finintel.parse.text_layer import read_text_layer
from finintel.tables import build_statement_table
from finintel.tables.headers import HeaderResult, read_headers
from finintel.tables.regions import statement_regions

SPECS = all_specs()
ENGINES: list[PdfplumberEngine | PymupdfTablesEngine] = [PdfplumberEngine(), PymupdfTablesEngine()]
REQUIRED = {
    "unit_thousands",  # £000
    "company_before_group",  # £m
    "missing_unit",
    "bare_dollar",
    "restated_header",
    "columnar_income_statement",
    "group_company_columns",
}


def _headers(
    path: Path, tmp_path: Path, engine: PdfplumberEngine | PymupdfTablesEngine
) -> HeaderResult:
    spec = load_spec(path)
    pdf = render(spec, tmp_path / f"{spec.name}.pdf")
    layer = read_text_layer(pdf)
    located = locate(layer)
    tables = {}
    for kind in (StatementType.INCOME_STATEMENT, StatementType.BALANCE_SHEET):
        location = located.statements[kind]
        clips = {r.page: [r.bbox] for r in statement_regions(layer, location)}
        tables[kind] = build_statement_table(
            layer, location, engine.parse(pdf, sorted(clips), clips)
        )
    return read_headers(tables, layer)


def test_every_m2_3_hazard_has_a_spec() -> None:
    assert {p.stem for p in SPECS} >= REQUIRED


@pytest.mark.parametrize("engine", ENGINES, ids=[e.name for e in ENGINES])
@pytest.mark.parametrize("path", SPECS, ids=[p.stem for p in SPECS])
def test_headers_match_the_spec(
    path: Path, engine: PdfplumberEngine | PymupdfTablesEngine, tmp_path: Path
) -> None:
    expect = load_spec(path).expect
    result = _headers(path, tmp_path, engine)
    assert result.status == expect.header_status, result.warnings
    assert result.currency == expect.currency
    assert result.unit_scale == expect.unit_scale
    got = {p.id: (p.end_date, p.is_restated) for p in result.periods}
    want = {p.id: (p.end_date, p.is_restated) for p in expect.periods}
    assert got == want
    for kind in (StatementType.INCOME_STATEMENT, StatementType.BALANCE_SHEET):
        values = [c for c in result.tables[kind].columns if c.kind.value == "value"]
        usable = [i for i, c in enumerate(values) if c.usable]
        assert usable == list(expect.usable_columns.get(kind.value, range(len(values))))
        for column in values:
            if not column.usable:
                assert column.excluded, "an unusable column always says why"


def test_blocking_statuses_say_what_they_saw(tmp_path: Path) -> None:
    missing = _headers(next(p for p in SPECS if p.stem == "missing_unit"), tmp_path, ENGINES[0])
    assert [w.code for w in missing.warnings if w.code == "unit_ambiguous"]
    assert all("no unit token" in w.message for w in missing.warnings if w.code == "unit_ambiguous")
    dollar = _headers(next(p for p in SPECS if p.stem == "bare_dollar"), tmp_path, ENGINES[0])
    [warning, *_] = [w for w in dollar.warnings if w.code == "currency_ambiguous"]
    assert '"$m"' in warning.message and "presentation currency" in warning.message


def test_restated_comparative_is_flagged(tmp_path: Path) -> None:
    result = _headers(next(p for p in SPECS if p.stem == "restated_header"), tmp_path, ENGINES[0])
    codes = [w.code for w in result.warnings]
    assert codes.count("restated_comparative") == 2  # income statement and balance sheet
    assert all("FY2024" in w.message for w in result.warnings if w.code == "restated_comparative")


def test_columnar_components_and_company_columns_say_why(tmp_path: Path) -> None:
    columnar = _headers(
        next(p for p in SPECS if p.stem == "columnar_income_statement"), tmp_path, ENGINES[0]
    )
    excluded = [
        c.excluded for c in columnar.tables[StatementType.INCOME_STATEMENT].columns if c.excluded
    ]
    assert len(excluded) == 4 and all("only the statutory total is used" in e for e in excluded)
    entity = _headers(
        next(p for p in SPECS if p.stem == "group_company_columns"), tmp_path, ENGINES[0]
    )
    columns = [
        c for c in entity.tables[StatementType.BALANCE_SHEET].columns if c.kind.value == "value"
    ]
    assert [c.entity for c in columns] == ["group", "group", "company", "company"]
    assert all("only group figures are used" in (c.excluded or "") for c in columns[2:])
