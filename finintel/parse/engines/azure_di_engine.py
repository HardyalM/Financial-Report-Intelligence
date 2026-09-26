"""AzureDiEngine: the `azure_di` table engine (image_layout family).

Raw call and storage in M1; normalisation and reconciliation in M2.5.
"""

from pathlib import Path

from finintel._placeholders import not_yet
from finintel.parse.engines.base import EngineFamily, ParsedTables


class AzureDiEngine:
    name = "azure_di"
    family = EngineFamily.IMAGE_LAYOUT

    def parse(self, pdf_path: Path, pages: list[int] | None = None) -> ParsedTables:
        not_yet("M1 (raw call) and M2.5", "AzureDiEngine.parse")
