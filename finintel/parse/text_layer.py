"""PyMuPDF text layer: words with bounding boxes, fonts, blocks, outline and page labels."""

from dataclasses import dataclass
from pathlib import Path

from finintel._placeholders import not_yet


@dataclass(frozen=True)
class TextLayer:
    """Words, boxes, fonts, outline and page labels. Fields are defined in M1."""


def read_text_layer(pdf_path: Path) -> TextLayer:
    """Read the embedded text layer of a digitally born PDF."""
    not_yet("M1", "read_text_layer")
