"""Write chunks and embeddings; read them back as an `IndexBackend` (RAG section 3.2).

Dense and lexical queries are filtered to one document, never run across documents. Tables
(`is_table`) are stored but excluded from retrieval in v1. Vectors travel as text literals cast
to `vector`, so no pgvector client package is needed.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

import psycopg

from finintel.narrative.models import Chunk
from finintel.retrieval.embeddings import Embedder
from finintel.retrieval.pipeline import PER_LIST


def _vec(v: Sequence[float]) -> str:
    return "[" + ",".join(f"{x:.8g}" for x in v) + "]"


def upsert_document(
    conn: psycopg.Connection, *, sha256: str, filename: str, page_count: int, document_type: str
) -> int:
    row = conn.execute(
        "INSERT INTO documents (sha256, filename, page_count, document_type) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (sha256) DO UPDATE SET "
        "document_type = EXCLUDED.document_type RETURNING id",
        (sha256, filename, page_count, document_type),
    ).fetchone()
    assert row is not None
    return int(row[0])


def store_chunks(
    conn: psycopg.Connection, document_id: int, chunks: Sequence[Chunk], embedder: Embedder
) -> None:
    """Replace this document's chunks of these ids, then embed the non-table ones."""
    with conn.transaction():
        for c in chunks:
            conn.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunker_version, text, page_start, "
                "page_end, char_page_map, line_boxes, section_id, heading_path, is_note, "
                "note_number, note_title, is_footnote, is_table) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (chunk_id) DO NOTHING",
                (
                    c.chunk_id, document_id, c.chunker_version, c.text, c.page_start, c.page_end,
                    json.dumps(c.char_page_map),
                    json.dumps([lb.model_dump(mode="json") for lb in c.line_boxes]),
                    c.section_id, list(c.heading_path), c.is_note, c.note_number, c.note_title,
                    c.is_footnote, c.is_table,
                ),
            )  # fmt: skip
        todo = [c for c in chunks if not c.is_table]
        for c, vec in zip(todo, embedder.embed([c.text for c in todo]), strict=True):
            conn.execute(
                "INSERT INTO chunk_embeddings (chunk_id, model_id, embedding) "
                "VALUES (%s, %s, %s::vector) ON CONFLICT DO NOTHING",
                (c.chunk_id, embedder.model_id, _vec(vec)),
            )


@dataclass(frozen=True)
class ChunkRow:
    chunk_id: str
    text: str
    section_id: str
    page_start: int
    page_end: int
    heading_path: tuple[str, ...]


class PostgresIndex:
    """`IndexBackend` over one document's chunks and one embedding model."""

    def __init__(self, conn: psycopg.Connection, document_id: int, embedder: Embedder) -> None:
        self._conn, self._doc, self._embedder = conn, document_id, embedder

    def dense(self, query: str, k: int = PER_LIST) -> list[str]:
        qv = _vec(self._embedder.embed([query])[0])
        rows = self._conn.execute(
            "SELECT c.chunk_id FROM chunk_embeddings e JOIN chunks c USING (chunk_id) "
            "WHERE c.document_id = %s AND e.model_id = %s AND NOT c.is_table "
            "ORDER BY e.embedding <=> %s::vector, c.chunk_id LIMIT %s",
            (self._doc, self._embedder.model_id, qv, k),
        ).fetchall()
        return [r[0] for r in rows]

    def lexical(self, query: str, k: int = PER_LIST) -> list[str]:
        rows = self._conn.execute(
            "WITH q AS (SELECT replace(plainto_tsquery('english', %s)::text, '&', '|')::tsquery "
            "AS q) "
            "SELECT chunk_id FROM chunks, q "
            "WHERE document_id = %s AND NOT is_table AND tsv @@ q.q "
            "ORDER BY ts_rank_cd(tsv, q.q) DESC, chunk_id LIMIT %s",
            (query, self._doc, k),
        ).fetchall()
        return [r[0] for r in rows]

    def chunk(self, chunk_id: str) -> ChunkRow:
        row = self._conn.execute(
            "SELECT chunk_id, text, section_id, page_start, page_end, heading_path "
            "FROM chunks WHERE chunk_id = %s AND document_id = %s",
            (chunk_id, self._doc),
        ).fetchone()
        if row is None:
            raise KeyError(chunk_id)
        return ChunkRow(row[0], row[1], row[2], row[3], row[4], tuple(row[5]))
