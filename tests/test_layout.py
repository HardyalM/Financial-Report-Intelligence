"""Package layout matches docs/ARCHITECTURE.md section 2, and every stub fails loudly."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from finintel.parse.engines.base import EngineFamily

MODULES = [
    "finintel.contracts",
    "finintel.ingest",
    "finintel.parse.text_layer",
    "finintel.parse.engines.base",
    "finintel.parse.engines.pdfplumber_engine",
    "finintel.parse.engines.pymupdf_tables_engine",
    "finintel.parse.engines.azure_di_engine",
    "finintel.parse.engines.vision_engine",
    "finintel.locate",
    "finintel.tables",
    "finintel.mapping",
    "finintel.reconcile",
    "finintel.review",
    "finintel.ratios",
    "finintel.narrative",
    "finintel.retrieval",
    "finintel.commentary",
    "finintel.commentary.validators",
    "finintel.commentary.render",
    "finintel.llm",
    "finintel.storage",
    "finintel.cache",
    "finintel.db",
    "finintel.api",
    "finintel.worker",
    "finintel.evals",
    "finintel.cli",
]

ENGINES = {
    "finintel.parse.engines.pdfplumber_engine:PdfplumberEngine": EngineFamily.TEXT_LAYER,
    "finintel.parse.engines.pymupdf_tables_engine:PymupdfTablesEngine": EngineFamily.TEXT_LAYER,
    "finintel.parse.engines.azure_di_engine:AzureDiEngine": EngineFamily.IMAGE_LAYOUT,
    "finintel.parse.engines.vision_engine:VisionEngine": EngineFamily.VISION,
}


@pytest.mark.parametrize("module", MODULES)
def test_module_imports(module: str) -> None:
    importlib.import_module(module)


@pytest.mark.parametrize(("target", "family"), ENGINES.items())
def test_engine_declares_its_family(target: str, family: EngineFamily) -> None:
    module_name, class_name = target.split(":")
    engine = getattr(importlib.import_module(module_name), class_name)()
    assert engine.family is family
    with pytest.raises(NotImplementedError, match=r"M\d"):
        engine.parse(Path("report.pdf"))


def test_stubs_name_their_session() -> None:
    from finintel.locate import locate_statements
    from finintel.ratios import compute_ratios

    with pytest.raises(NotImplementedError, match=r"M2\.1"):
        locate_statements(None)
    with pytest.raises(NotImplementedError, match="M3"):
        compute_ratios(None)  # type: ignore[arg-type]


def test_cli_without_a_command_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    from finintel.cli import main

    assert main([]) == 2
    assert "inspect" in capsys.readouterr().err
