"""Both text-layer engines return ParsedTables: every cell as the engine produced it."""

from __future__ import annotations

from pathlib import Path

import pytest

from finintel.parse.engines.base import EngineFamily
from finintel.parse.engines.pdfplumber_engine import PdfplumberEngine
from finintel.parse.engines.pymupdf_tables_engine import PymupdfTablesEngine
from tests.inspect.synthetic import mini_report, ruled_table_pdf

ENGINES: list[PdfplumberEngine | PymupdfTablesEngine] = [PdfplumberEngine(), PymupdfTablesEngine()]


@pytest.mark.parametrize("engine", ENGINES, ids=[e.name for e in ENGINES])
def test_ruled_table_both_strategies(
    engine: PdfplumberEngine | PymupdfTablesEngine, tmp_path: Path
) -> None:
    parsed = engine.parse(ruled_table_pdf(tmp_path / "ruled.pdf"))
    assert parsed.engine == engine.name and parsed.family is EngineFamily.TEXT_LAYER
    assert parsed.errors == ()
    [lines] = parsed.on_page(1, "lines")
    texts = {(c.row, c.col): c.text for c in lines.cells}
    assert texts[(1, 0)] == "Revenue" and texts[(1, 1)] == "13,907.5" and texts[(2, 1)] == "(250.0)"
    assert lines.n_rows == 3 and lines.n_cols == 3
    assert all(c.bbox is not None for c in lines.cells)


@pytest.mark.parametrize("engine", ENGINES, ids=[e.name for e in ENGINES])
def test_clip_restricts_the_region(
    engine: PdfplumberEngine | PymupdfTablesEngine, tmp_path: Path
) -> None:
    pdf = mini_report(tmp_path / "mini.pdf")
    clip = (0.0, 140.0, 595.0, 200.0)  # the header and first rows of the income statement only
    parsed = engine.parse(pdf, [3], {3: [clip]})
    assert parsed.tables and all(t.page == 3 and t.clip == clip for t in parsed.tables)
    for table in parsed.tables:
        for cell in table.cells:
            if cell.bbox is not None and cell.text:
                assert cell.bbox[1] >= clip[1] - 2 and cell.bbox[3] <= clip[3] + 2
    texts = {c.text for t in parsed.tables for c in t.cells if c.text}
    assert "(1,902.1)" not in texts  # a row below the clip


@pytest.mark.parametrize("engine", ENGINES, ids=[e.name for e in ENGINES])
def test_page_range_is_checked(
    engine: PdfplumberEngine | PymupdfTablesEngine, tmp_path: Path
) -> None:
    pdf = mini_report(tmp_path / "mini.pdf")
    with pytest.raises(IndexError):
        engine.parse(pdf, [8])


def test_no_stdout_advice_from_pymupdf(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    PymupdfTablesEngine().parse(mini_report(tmp_path / "mini.pdf"), [3])
    assert capsys.readouterr().out == ""
