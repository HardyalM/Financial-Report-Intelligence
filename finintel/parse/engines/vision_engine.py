"""VisionEngine: the `vision` table engine (vision family). Implemented in M2.6 (optional)."""

from pathlib import Path

from finintel._placeholders import not_yet
from finintel.parse.engines.base import EngineFamily, ParsedTables


class VisionEngine:
    name = "vision"
    family = EngineFamily.VISION

    def parse(self, pdf_path: Path, pages: list[int] | None = None) -> ParsedTables:
        not_yet("M2.6 (optional)", "VisionEngine.parse")
