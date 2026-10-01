"""API tests: the real app and worker over a throwaway Postgres schema, in-process HTTP client."""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from finintel.api import create_app
from finintel.db.migrate import database_url, migrate
from finintel.retrieval.embeddings import FakeEmbedder
from finintel.storage import FilesystemStore
from finintel.worker.context import Hooks, RunContext

ROOT = Path(__file__).resolve().parents[2]
EXCERPT = ROOT / "tests" / "golden" / "company_a" / "excerpt.pdf"

pytestmark = pytest.mark.network


@pytest.fixture
def schema() -> Iterator[str]:
    try:
        c = psycopg.connect(database_url(), autocommit=True, connect_timeout=2)
    except psycopg.OperationalError as exc:
        pytest.skip(f"postgres unreachable: {type(exc).__name__}")
    name = "a_" + uuid.uuid4().hex[:10]
    c.execute(f"CREATE SCHEMA {name}")
    c.execute(f"SET search_path TO {name}, public")
    migrate(c)
    yield name
    c.execute(f"DROP SCHEMA {name} CASCADE")
    c.close()


@pytest.fixture
def executed() -> Counter[str]:
    return Counter()


@pytest.fixture
def ctx(tmp_path: Path, executed: Counter[str]) -> RunContext:
    return RunContext(
        store=FilesystemStore(tmp_path / "store"), cache_dir=tmp_path / "cache",
        embedder=FakeEmbedder(), provider=None, backoff_s=0.01, lease_s=0.0,
        hooks=Hooks(on_execute=lambda stage: executed.update([stage])),
    )  # fmt: skip


@pytest.fixture
def db(schema: str) -> Iterator[psycopg.Connection]:
    c = psycopg.connect(database_url(), autocommit=True)
    c.execute(f"SET search_path TO {schema}, public")
    yield c
    c.close()


@pytest.fixture
def client(schema: str, ctx: RunContext) -> Iterator[TestClient]:
    def connect() -> psycopg.Connection:
        c = psycopg.connect(database_url(), autocommit=True)
        c.execute(f"SET search_path TO {schema}, public")
        return c

    with TestClient(create_app(ctx, connect, run_inline=True)) as c:
        yield c


def upload(client: TestClient, path: Path = EXCERPT, name: str | None = None) -> dict[str, object]:
    with path.open("rb") as f:
        r = client.post("/uploads", files={"file": (name or path.name, f, "application/pdf")})
    assert r.status_code in (200, 202), r.text
    body: dict[str, object] = r.json()
    return body


def encrypted_pdf(path: Path) -> Path:
    """A password-protected PDF (the upload must be refused with 422 encrypted_pdf)."""
    import pymupdf

    pm: Any = pymupdf
    doc = pm.open()
    doc.new_page().insert_text((50, 50), "secret")
    doc.save(path, encryption=pm.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw")
    return path
