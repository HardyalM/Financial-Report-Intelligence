"""`finintel run <pdf>`: submit a report and run the worker until its pipeline is done (M6.1).

    finintel run fixtures/pdfs/company_a.pdf [--engines local|all] [--embedder bge-m3|fake]

Needs Postgres (DATABASE_URL, `docker compose up -d db && make migrate`). Provider selection is the
same as `finintel commentary` (FININTEL_PROVIDER; none gives extractive commentary). Exit codes: 0
document `ready`; 1 any other end state (blocked on a person, or failed).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TextIO

import psycopg

from finintel.cli.common import resolve_pdf
from finintel.cli.settings import read_dotenv
from finintel.db.migrate import database_url
from finintel.llm.providers import select_provider
from finintel.parse.engines.azure_di_engine import AzureDiConfig, AzureDiEngine
from finintel.retrieval.embeddings import Embedder, FakeEmbedder
from finintel.retrieval.local_models import BgeM3Embedder, MemoEmbedder
from finintel.storage import FilesystemStore
from finintel.worker.context import RunContext
from finintel.worker.runner import run_until_idle, submit_pdf


def build_context(
    env: Mapping[str, str], artifacts: Path, cache_dir: Path, *, engines: str, embedder: str
) -> RunContext:
    emb: Embedder = (
        MemoEmbedder(BgeM3Embedder(), cache_dir / "embeddings")
        if embedder == "bge-m3"
        else FakeEmbedder()
    )
    azure_config = AzureDiConfig.from_env(env)
    return RunContext(
        store=FilesystemStore(artifacts / "store"),
        cache_dir=cache_dir,
        embedder=emb,
        provider=select_provider(env),
        azure=AzureDiEngine(azure_config) if azure_config else None,
        engines=engines,
    )


def summarise(conn: psycopg.Connection, document_id: int) -> dict[str, Any]:
    doc = conn.execute(
        "SELECT status, document_type, page_count FROM documents WHERE id = %s", (document_id,)
    ).fetchone()
    pack = conn.execute(
        "SELECT pack_sha FROM statement_packs WHERE document_id = %s ORDER BY version DESC LIMIT 1",
        (document_id,),
    ).fetchone()
    stages = conn.execute(
        "SELECT stage, status, attempts, error_code FROM jobs WHERE document_id = %s ORDER BY ordinal",
        (document_id,),
    ).fetchall()
    return {
        "status": doc[0] if doc else None,
        "document_type": doc[1] if doc else None,
        "pack_sha": pack[0] if pack else None,
        "jobs": [{"stage": s, "status": st, "attempts": a, "error": e} for s, st, a, e in stages],
    }


def run_pipeline(
    target: str, artifacts: Path, cache_dir: Path, *, engines: str, embedder: str, out: TextIO
) -> int:
    pdf = resolve_pdf(target)
    env = {**read_dotenv(Path(".env")), **os.environ}
    ctx = build_context(env, artifacts, cache_dir, engines=engines, embedder=embedder)
    with psycopg.connect(database_url(), autocommit=True) as conn:
        document_id = submit_pdf(conn, ctx, pdf)
        run_until_idle(conn, ctx)
        result = summarise(conn, document_id)
    print(f"{pdf.name}: document {document_id} status={result['status']}", file=out)
    print(f"  pack_sha {result['pack_sha']}", file=out)
    for job in result["jobs"]:
        err = f"  {job['error']}" if job["error"] else ""
        print(f"  {job['stage']:<11} {job['status']:<8} attempts={job['attempts']}{err}", file=out)
    return 0 if result["status"] == "ready" else 1
