"""Postgres index against a real database (docker compose up -d db && make migrate).

Skipped, with a reason, when the database is unreachable: unit CI has no Docker. Each test works
in a throwaway schema, so it never touches real data.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import psycopg
import pytest

from finintel.db.migrate import database_url, migrate
from finintel.db.store import PostgresIndex, store_chunks, upsert_document
from finintel.locate.models import DocumentType
from finintel.retrieval.embeddings import FakeEmbedder
from finintel.retrieval.pipeline import OverlapReranker, retrieve_all
from tests.retrieval.test_retrieval import _chunk

pytestmark = pytest.mark.network  # loopback to local Postgres; never in the default run


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    try:
        c = psycopg.connect(database_url(), autocommit=True, connect_timeout=2)
    except psycopg.OperationalError as exc:
        pytest.skip(f"postgres unreachable: {type(exc).__name__}")
    schema = "t_" + uuid.uuid4().hex[:10]
    c.execute(f"CREATE SCHEMA {schema}")
    c.execute(f"SET search_path TO {schema}, public")
    migrate(c)
    yield c
    c.execute(f"DROP SCHEMA {schema} CASCADE")
    c.close()


def _doc(conn: psycopg.Connection, sha: str) -> int:
    return upsert_document(
        conn, sha256=sha, filename="x.pdf", page_count=3, document_type="corporate"
    )


def test_migrate_is_idempotent(conn: psycopg.Connection) -> None:
    assert migrate(conn) == []


def test_dense_and_lexical_are_filtered_to_the_document(conn: psycopg.Connection) -> None:
    emb = FakeEmbedder()
    a, b = _doc(conn, "a" * 64), _doc(conn, "b" * 64)
    store_chunks(conn, a, [_chunk("a1", "principal risks and uncertainties")], emb)
    store_chunks(conn, b, [_chunk("b1", "principal risks and uncertainties")], emb)
    index = PostgresIndex(conn, a, emb)
    assert index.dense("principal risks", 10) == ["a1"]
    assert index.lexical("principal risks", 10) == ["a1"]


def test_tables_are_stored_but_not_retrieved(conn: psycopg.Connection) -> None:
    emb = FakeEmbedder()
    d = _doc(conn, "c" * 64)
    store_chunks(
        conn, d, [_chunk("p", "going concern basis"), _chunk("t", "going concern", table=True)], emb
    )
    index = PostgresIndex(conn, d, emb)
    assert index.dense("going concern", 10) == ["p"]
    assert index.lexical("going concern", 10) == ["p"]
    assert conn.execute("SELECT count(*) FROM chunks WHERE is_table").fetchone() == (1,)


def test_store_is_idempotent_and_row_roundtrips(conn: psycopg.Connection) -> None:
    emb = FakeEmbedder()
    d = _doc(conn, "d" * 64)
    chunks = [_chunk("p", "going concern basis", "going_concern")]
    store_chunks(conn, d, chunks, emb)
    store_chunks(conn, d, chunks, emb)
    row = PostgresIndex(conn, d, emb).chunk("p")
    assert row.section_id == "going_concern" and row.heading_path == ("going_concern",)
    assert conn.execute("SELECT count(*) FROM chunk_embeddings").fetchone() == (1,)


def test_postgres_and_memory_backends_agree(conn: psycopg.Connection) -> None:
    from finintel.retrieval.pipeline import InMemoryIndex

    emb = FakeEmbedder()
    chunks = [
        _chunk(
            "r1",
            "principal risks and uncertainties include supply chain disruption",
            "principal_risks",
        ),
        _chunk("r2", "emerging risks and risk mitigations and risk appetite were reviewed"),
        _chunk("g1", "going concern assessment and conclusion by the board", "going_concern"),
        _chunk("x1", "the canteen menu changed in the spring"),
    ]
    d = _doc(conn, "e" * 64)
    store_chunks(conn, d, chunks, emb)
    pg = retrieve_all(DocumentType.CORPORATE, PostgresIndex(conn, d, emb), OverlapReranker())
    mem = retrieve_all(DocumentType.CORPORATE, InMemoryIndex(chunks, emb), OverlapReranker())
    for p, m in zip(pg, mem, strict=True):
        assert p.status == m.status
        assert {c.chunk_id for c in p.chunks} == {c.chunk_id for c in m.chunks}
