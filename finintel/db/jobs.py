"""The jobs table as a queue: one row per (document, stage), claimed with FOR UPDATE SKIP LOCKED.

A job is runnable when it is queued, its backoff has passed, its document is still processing, and
every earlier stage of that document is done. Completion is recorded in the same transaction as
the stage's outputs (see worker.runner), so a stage is either fully done or not done: it never
runs again once done, and a crash mid-stage leaves a `running` row that `recover` re-queues.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import psycopg


@dataclass(frozen=True)
class Job:
    id: int
    document_id: int
    stage: str
    attempts: int  # including this run


def enqueue(conn: psycopg.Connection, document_id: int, stages: Sequence[str]) -> None:
    """Create one queued job per stage. Idempotent: an existing job (any status) is left alone."""
    with conn.transaction():
        for ordinal, stage in enumerate(stages):
            conn.execute(
                "INSERT INTO jobs (document_id, stage, ordinal) VALUES (%s, %s, %s) "
                "ON CONFLICT (document_id, stage) DO NOTHING",
                (document_id, stage, ordinal),
            )


def claim(conn: psycopg.Connection) -> Job | None:
    """Claim the next runnable job, or None. Safe with several workers (SKIP LOCKED)."""
    with conn.transaction():
        row = conn.execute(
            "SELECT j.id, j.document_id, j.stage FROM jobs j "
            "JOIN documents d ON d.id = j.document_id "
            "WHERE j.status = 'queued' AND j.run_after <= now() "
            "AND d.status IN ('queued', 'processing') "
            "AND NOT EXISTS (SELECT 1 FROM jobs p WHERE p.document_id = j.document_id "
            "AND p.ordinal < j.ordinal AND p.status <> 'done') "
            "ORDER BY j.document_id, j.ordinal FOR UPDATE OF j SKIP LOCKED LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        updated = conn.execute(
            "UPDATE jobs SET status = 'running', attempts = attempts + 1, started_at = now(), "
            "error_code = NULL WHERE id = %s RETURNING attempts",
            (row[0],),
        ).fetchone()
        assert updated is not None
        conn.execute(
            "UPDATE documents SET status = 'processing' WHERE id = %s AND status = 'queued'",
            (row[1],),
        )
        return Job(id=row[0], document_id=row[1], stage=row[2], attempts=updated[0])


def recover(conn: psycopg.Connection, lease_s: float) -> int:
    """Re-queue jobs left `running` by a worker that died (older than the lease)."""
    with conn.transaction():
        cur = conn.execute(
            "UPDATE jobs SET status = 'queued' WHERE status = 'running' "
            "AND started_at <= now() - make_interval(secs => %s)",
            (lease_s,),
        )
        return cur.rowcount


def mark_done(conn: psycopg.Connection, job_id: int) -> None:
    conn.execute(
        "UPDATE jobs SET status = 'done', finished_at = now(), error_code = NULL WHERE id = %s",
        (job_id,),
    )


def mark_failed(
    conn: psycopg.Connection, job: Job, error_code: str, max_attempts: int, backoff_s: float
) -> bool:
    """Record a failed attempt. Returns True when it will be retried (attempts remain)."""
    retry = job.attempts < max_attempts
    delay = backoff_s * (2 ** (job.attempts - 1))
    with conn.transaction():
        if retry:
            conn.execute(
                "UPDATE jobs SET status = 'queued', error_code = %s, "
                "run_after = now() + make_interval(secs => %s) WHERE id = %s",
                (error_code, delay, job.id),
            )
        else:
            conn.execute(
                "UPDATE jobs SET status = 'failed', error_code = %s, finished_at = now() "
                "WHERE id = %s",
                (error_code, job.id),
            )
            conn.execute("UPDATE documents SET status = 'failed' WHERE id = %s", (job.document_id,))
    return retry


def reset(conn: psycopg.Connection, document_id: int, stages: Sequence[str]) -> None:
    """Queue the given stages again (and mark the document processing). Used when a person's
    decision changes an input: the affected stages re-run, the rest are left done."""
    with conn.transaction():
        conn.execute(
            "UPDATE jobs SET status = 'queued', attempts = 0, error_code = NULL, "
            "run_after = now(), finished_at = NULL WHERE document_id = %s AND stage = ANY(%s)",
            (document_id, list(stages)),
        )
        conn.execute("UPDATE documents SET status = 'processing' WHERE id = %s", (document_id,))
