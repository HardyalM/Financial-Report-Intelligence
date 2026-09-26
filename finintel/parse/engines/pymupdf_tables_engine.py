"""PymupdfTablesEngine: the `pymupdf_tables` engine (text_layer family). Implemented in M2.2."""

from pathlib import Path

from finintel._placeholders import not_yet
from finintel.parse.engines.base import EngineFamily, ParsedTables


class PymupdfTablesEngine:
    name = "pymupdf_tables"
    family = EngineFamily.TEXT_LAYER

    def parse(self, pdf_path: Path, pages: list[int] | None = None) -> ParsedTables:
        not_yet("M2.2", "PymupdfTablesEngine.parse")
