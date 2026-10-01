"""Every table and column of ARCHITECTURE section 2.1 exists (M6.1 gate)."""

from __future__ import annotations

import re

import psycopg
import pytest

from tests.worker.conftest import ROOT

pytestmark = pytest.mark.network


def documented_tables() -> dict[str, set[str]]:
    """Parse the section 2.1 table: first backticked name of each top-level comma-separated entry."""
    text = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    block = text.split("### 2.1 Data model", 1)[1].split("\n---", 1)[0]
    tables: dict[str, set[str]] = {}
    for line in block.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not cells[0].startswith("`"):
            continue
        name = cells[0].strip("`")
        columns: set[str] = set()
        depth, current = 0, ""
        for ch in cells[1] + ",":
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch == "," and depth == 0:
                m = re.search(r"`([a-z_]+)`", current)
                if m:
                    columns.add(m.group(1))
                current = ""
            else:
                current += ch
        tables[name] = columns
    return tables


def test_the_documented_model_has_every_table() -> None:
    assert set(documented_tables()) == {
        "documents", "jobs", "statement_packs", "extraction_reports", "review_items",
        "overrides", "ratio_packs", "chunks", "chunk_embeddings", "commentaries",
    }  # fmt: skip


def test_every_documented_table_and_column_exists(conn: psycopg.Connection) -> None:
    rows = conn.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema()"
    ).fetchall()
    actual: dict[str, set[str]] = {}
    for table, column in rows:
        actual.setdefault(table, set()).add(column)
    missing = {
        t: sorted(cols - actual.get(t, set())) for t, cols in documented_tables().items()
        if cols - actual.get(t, set())
    }  # fmt: skip
    assert missing == {}


def test_overrides_are_append_only(conn: psycopg.Connection) -> None:
    doc = conn.execute(
        "INSERT INTO documents (sha256, filename, page_count) VALUES ('s', 'f', 1) RETURNING id"
    ).fetchone()
    assert doc is not None
    conn.execute(
        "INSERT INTO overrides (document_id, action, payload, anchored) VALUES (%s, 'set_value', '{}', true)",
        (doc[0],),
    )
    for sql in ("UPDATE overrides SET reason = 'x'", "DELETE FROM overrides"):
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            conn.execute(sql)
