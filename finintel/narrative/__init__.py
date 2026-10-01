"""Section tree, table-region detection and structure-aware chunking (RAG sections 1-2)."""

from finintel.narrative.chunker import build_chunks, estimate_tokens
from finintel.narrative.models import CHUNKER_VERSION, Chunk, LineBox
from finintel.narrative.sections import EXCLUDED, classify

__all__ = [
    "CHUNKER_VERSION",
    "EXCLUDED",
    "Chunk",
    "LineBox",
    "build_chunks",
    "classify",
    "estimate_tokens",
]
