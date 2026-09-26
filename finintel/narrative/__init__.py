"""Section tree, table-region detection and structure-aware chunking (RAG sections 1-2)."""

from dataclasses import dataclass
from typing import Any

from finintel._placeholders import not_yet


@dataclass(frozen=True)
class Chunk:
    """A citable narrative chunk with its char-to-page map. Fields are defined in M4.1."""


def build_chunks(text_layer: Any) -> list[Chunk]:
    """Chunk narrative sections; tables and primary statements never enter prose chunks."""
    not_yet("M4.1", "build_chunks")
