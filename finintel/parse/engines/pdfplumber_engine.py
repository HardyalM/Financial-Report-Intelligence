"""PdfplumberEngine: the `pdfplumber` table engine (text_layer family). Implemented in M1."""

from pathlib import Path

from finintel._placeholders import not_yet
from finintel.parse.engines.base import EngineFamily, ParsedTables


class PdfplumberEngine:
    name = "pdfplumber"
    family = EngineFamily.TEXT_LAYER

    def parse(self, pdf_path: Path, pages: list[int] | None = None) -> ParsedTables:
        not_yet("M1", "PdfplumberEngine.parse")
