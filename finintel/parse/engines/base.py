"""Engine interface shared by every table engine (EXTRACTION section 5.1a)."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class EngineFamily(StrEnum):
    """Agreement counts only across families (EXTRACTION section 5.1a)."""

    IMAGE_LAYOUT = "image_layout"
    TEXT_LAYER = "text_layer"
    VISION = "vision"


@dataclass(frozen=True)
class ParsedTables:
    """Engine output normalised to one shape. Fields are defined in M1 and M2.2."""


class TableEngine(Protocol):
    """A table engine. Engines propose cells; the text layer decides row, column and period."""

    name: str
    family: EngineFamily

    def parse(self, pdf_path: Path, pages: list[int] | None = None) -> ParsedTables:
        """Parse the given 1-based PDF pages (all pages if None)."""
        ...
