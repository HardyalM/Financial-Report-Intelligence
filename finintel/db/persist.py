"""Write pipeline outputs to Postgres (ARCHITECTURE 2.1). Callers wrap these in one transaction."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

import psycopg

_WARNING_KIND = {
    "parser_disagreement": "disagreement",
    "document_type_ambiguous": "document_type",
    "entity_scope_ambiguous": "scope",
    "unit_ambiguous": "unit",
    "currency_ambiguous": "unit",
}


def _j(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


def store_pack(
    conn: psycopg.Connection, document_id: int, pack: Mapping[str, Any], pack_sha: str, source: str
) -> int:
    """A new pack version (1 for the first). Returns the pack id."""
    row = conn.execute(
        "INSERT INTO statement_packs (document_id, version, pack, pack_sha, source) "
        "VALUES (%s, COALESCE((SELECT max(version) FROM statement_packs WHERE document_id = %s), 0) + 1, "
        "%s::jsonb, %s, %s) RETURNING id",
        (document_id, document_id, _j(pack), pack_sha, source),
    ).fetchone()
    assert row is not None
    return int(row[0])


def store_report(
    conn: psycopg.Connection, document_id: int, pack_id: int, report: Mapping[str, Any]
) -> None:
    conn.execute(
        "INSERT INTO extraction_reports (document_id, pack_id, report) VALUES (%s, %s, %s::jsonb) "
        "ON CONFLICT (pack_id) DO UPDATE SET report = EXCLUDED.report",
        (document_id, pack_id, _j(report)),
    )


def store_review_items(
    conn: psycopg.Connection,
    document_id: int,
    suggestions: Sequence[Mapping[str, Any]],
    warnings: Sequence[Mapping[str, Any]],
) -> int:
    """Review queue rows: LLM pointers (never published) and warnings that need a person."""
    conn.execute(
        "DELETE FROM review_items WHERE document_id = %s AND status = 'open'", (document_id,)
    )
    count = 0
    for s in suggestions:
        conn.execute(
            "INSERT INTO review_items (document_id, item, period_id, kind, candidates) "
            "VALUES (%s, %s, %s, 'llm_suggestion', %s::jsonb)",
            (document_id, s.get("item"), s.get("period_id"), _j([dict(s)])),
        )
        count += 1
    for w in warnings:
        kind = _WARNING_KIND.get(str(w.get("code")))
        if kind is None:
            continue
        conn.execute(
            "INSERT INTO review_items (document_id, item, period_id, kind, candidates) "
            "VALUES (%s, %s, %s, %s, %s::jsonb)",
            (document_id, w.get("item"), w.get("period_id"), kind, _j([dict(w)])),
        )
        count += 1
    return count


def store_ratio_pack(
    conn: psycopg.Connection, statement_pack_id: int, ratios: Mapping[str, Any]
) -> int:
    row = conn.execute(
        "INSERT INTO ratio_packs (statement_pack_id, pack) VALUES (%s, %s::jsonb) RETURNING id",
        (statement_pack_id, _j(ratios)),
    ).fetchone()
    assert row is not None
    return int(row[0])


def store_commentary(
    conn: psycopg.Connection,
    *,
    document_id: int,
    statement_pack_id: int,
    ratio_pack_id: int,
    chunker_version: str,
    model_id: str | None,
    prompt_version: str | None,
    query_set_version: str,
    retrieval_set: Any,
    raw_output: Any,
    output: Mapping[str, Any],
    validation: Mapping[str, Any],
    trace_id: str | None = None,
) -> int:
    row = conn.execute(
        "INSERT INTO commentaries (document_id, statement_pack_id, ratio_pack_id, chunker_version, "
        "model_id, prompt_version, query_set_version, retrieval_set, raw_output, output, validation, "
        "trace_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s) "
        "RETURNING id",
        (
            document_id, statement_pack_id, ratio_pack_id, chunker_version, model_id, prompt_version,
            query_set_version, _j(retrieval_set), _j(raw_output), _j(output), _j(validation), trace_id,
        ),
    ).fetchone()  # fmt: skip
    assert row is not None
    return int(row[0])


def set_document(
    conn: psycopg.Connection, document_id: int, *, status: str | None = None,
    document_type: str | None = None, page_count: int | None = None,
) -> None:  # fmt: skip
    conn.execute(
        "UPDATE documents SET status = COALESCE(%s, status), document_type = COALESCE(%s, document_type), "
        "page_count = COALESCE(%s, page_count) WHERE id = %s",
        (status, document_type, page_count, document_id),
    )


def clear_chunks(conn: psycopg.Connection, document_id: int) -> None:
    """Idempotent re-index: embeddings go with their chunks (ON DELETE CASCADE)."""
    conn.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
