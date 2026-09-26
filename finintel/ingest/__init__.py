"""Upload intake: SHA-256, size and encryption checks, digital-born score, storing the original."""

from dataclasses import dataclass
from pathlib import Path

from finintel._placeholders import not_yet


@dataclass(frozen=True)
class DocumentRecord:
    """A stored upload. Fields are defined in M1."""


def ingest(pdf_path: Path) -> DocumentRecord:
    """Hash, check and store a PDF (EXTRACTION section 0)."""
    not_yet("M1", "ingest")
