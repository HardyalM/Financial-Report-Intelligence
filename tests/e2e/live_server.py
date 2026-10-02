"""The real API and worker for the M7.3 end-to-end tests, on a throwaway Postgres schema.

    uv run python -m tests.e2e.live_server --port 8765

Started by Playwright (web/playwright.config.ts, E2E_LIVE=1). Everything is the product's own code
(`create_app` with a background worker, the real stages, the real review endpoints); only the
inputs are pinned for a test: local engines, no model (extractive commentary), the deterministic
FakeEmbedder, a temporary object store, and a schema of its own that is dropped on exit. A short
pause inside each stage (`--stage-delay`) keeps the progress stepper observable; it changes no
outcome. Needs Postgres (`docker compose up -d db`).
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
import uuid
from pathlib import Path

import psycopg
import uvicorn

from finintel.api import create_app
from finintel.db.migrate import database_url, migrate
from finintel.retrieval.embeddings import FakeEmbedder
from finintel.storage import FilesystemStore
from finintel.worker.context import Hooks, RunContext


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--stage-delay", type=float, default=0.4)
    parser.add_argument("--drop-only", action="store_true", help="drop e2e_* schemas and exit")
    args = parser.parse_args()

    schema = "e2e_" + uuid.uuid4().hex[:10]
    try:
        admin = psycopg.connect(database_url(), autocommit=True, connect_timeout=3)
    except psycopg.OperationalError as exc:
        print(
            f"postgres unreachable ({type(exc).__name__}): start it with `docker compose up -d db`",
            file=sys.stderr,
        )
        return 2
    # Playwright stops this server through `uv run`, which may not pass the signal on, so a
    # schema can outlive its run. Only this harness creates e2e_* schemas, and live runs are
    # serial (one server), so any left over is a previous run's: drop it before starting.
    for (old,) in admin.execute(
        "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'e2e\\_%'"
    ).fetchall():
        admin.execute(f'DROP SCHEMA "{old}" CASCADE')
    if args.drop_only:
        admin.close()
        return 0
    admin.execute(f"CREATE SCHEMA {schema}")
    admin.execute(f"SET search_path TO {schema}, public")
    migrate(admin)

    def connect() -> psycopg.Connection:
        c = psycopg.connect(database_url(), autocommit=True)
        c.execute(f"SET search_path TO {schema}, public")
        return c

    work = Path(tempfile.mkdtemp(prefix="finintel-e2e-"))
    ctx = RunContext(
        store=FilesystemStore(work / "store"), cache_dir=work / "cache", embedder=FakeEmbedder(),
        provider=None, backoff_s=0.2, lease_s=60.0,
        hooks=Hooks(during_stage=lambda _stage: time.sleep(args.stage_delay)),
    )  # fmt: skip

    # uvicorn handles SIGINT and SIGTERM itself and returns, so the schema is dropped below.
    try:
        uvicorn.run(
            create_app(ctx, connect, start_worker=True),
            host="127.0.0.1", port=args.port, log_level="warning",
        )  # fmt: skip
    finally:
        admin.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        admin.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
