"""Hybrid retrieval: full-text search, vectors, RRF, rerank and evidence floor (RAG section 3)."""

from dataclasses import dataclass

from finintel._placeholders import not_yet


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk with its scores and query-set version. Fields are defined in M4.2."""


def retrieve(document_id: str, topic: str) -> list[RetrievedChunk]:
    """Run the versioned query set for one topic."""
    not_yet("M4.2", "retrieve")
