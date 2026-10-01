"""Apply `migrations/*.sql` in filename order, once each. `python -m finintel.db migrate`."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
DEFAULT_URL = "postgresql://finintel:finintel@localhost:5432/finintel"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_URL)


def migrate(conn: psycopg.Connection, directory: Path = MIGRATIONS) -> list[str]:
    """Returns the names applied by this call. Each file runs in its own transaction."""
    with conn.transaction():
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
    done = {r[0] for r in conn.execute("SELECT name FROM schema_migrations").fetchall()}
    applied: list[str] = []
    for path in sorted(directory.glob("*.sql")):
        if path.name in done:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8").encode())
            conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
        applied.append(path.name)
    return applied


def main(argv: list[str]) -> int:
    if argv != ["migrate"]:
        print("usage: python -m finintel.db migrate", file=sys.stderr)
        return 2
    with psycopg.connect(database_url(), autocommit=True) as conn:
        applied = migrate(conn)
    print("applied: " + (", ".join(applied) if applied else "nothing (up to date)"))
    return 0
