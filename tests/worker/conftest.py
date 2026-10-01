"""Worker tests run against real Postgres in a throwaway schema (make test-db). Skipped if absent."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from finintel.db.migrate import database_url, migrate
from finintel.retrieval.embeddings import FakeEmbedder
from finintel.storage import FilesystemStore
from finintel.worker.context import RunContext

ROOT = Path(__file__).resolve().parents[2]
EXCERPT = ROOT / "tests" / "golden" / "company_a" / "excerpt.pdf"

pytestmark = pytest.mark.network  # loopback to local Postgres; never in the default run


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    try:
        c = psycopg.connect(database_url(), autocommit=True, connect_timeout=2)
    except psycopg.OperationalError as exc:
        pytest.skip(f"postgres unreachable: {type(exc).__name__}")
    schema = "w_" + uuid.uuid4().hex[:10]
    c.execute(f"CREATE SCHEMA {schema}")
    c.execute(f"SET search_path TO {schema}, public")
    migrate(c)
    yield c
    c.execute(f"DROP SCHEMA {schema} CASCADE")
    c.close()


@pytest.fixture
def ctx(tmp_path: Path) -> RunContext:
    return RunContext(
        store=FilesystemStore(tmp_path / "store"),
        cache_dir=tmp_path / "cache",
        embedder=FakeEmbedder(),
        provider=None,
        backoff_s=0.01,
        lease_s=0.0,
    )
