"""The worker: claim a job, run its stage in one transaction, record done in the same transaction.

Crash safety: outputs and `done` commit together. A worker that dies mid-stage rolls back, leaving a
`running` job that `recover` re-queues after the lease; a stage that committed is never run again.
Failures are retried up to `max_attempts` with exponential backoff, then fail the document with a
classified error code (parse, map, retrieve, generate).
"""

from __future__ import annotations

import time
from pathlib import Path

import psycopg
import structlog

from finintel.db import jobs, persist
from finintel.db.store import upsert_document
from finintel.ingest import ingest
from finintel.worker.context import InjectedCrash, RunContext
from finintel.worker.stages import FAILURE_CLASS, STAGE_FUNCS, STAGES, load_doc

log = structlog.get_logger(__name__)


def submit_pdf(conn: psycopg.Connection, ctx: RunContext, pdf: Path) -> int:
    """Intake: check, store the original under its SHA-256, create the document, enqueue stages.
    The same file returns the same document id and enqueues nothing twice."""
    record = ingest(pdf)  # raises IngestError (not a PDF, too large, encrypted, unreadable)
    # The original keeps its own name: the filename is part of the pack source.
    key = f"sha256/{record.sha256}/{Path(record.filename).name}"
    if not ctx.store.exists(key):
        ctx.store.put(key, pdf.read_bytes())
    with conn.transaction():
        doc_id = upsert_document(
            conn, sha256=record.sha256, filename=record.filename,
            page_count=record.page_count, document_type="other",
        )  # fmt: skip
        conn.execute("UPDATE documents SET storage_key = %s WHERE id = %s", (key, doc_id))
        jobs.enqueue(conn, doc_id, STAGES)
    return doc_id


def run_one(conn: psycopg.Connection, ctx: RunContext) -> bool:
    """Run one runnable job. Returns False when there is none."""
    job = jobs.claim(conn)
    if job is None:
        return False
    started = time.monotonic()
    hooks = ctx.hooks
    try:
        with conn.transaction():
            doc = load_doc(conn, job.document_id)
            if hooks.on_execute:
                hooks.on_execute(job.stage)
            outcome = STAGE_FUNCS[job.stage](conn, ctx, doc)
            if hooks.during_stage:
                hooks.during_stage(job.stage)
            jobs.mark_done(conn, job.id)
            if outcome.halt is not None:
                persist.set_document(conn, doc.id, status=outcome.halt)
            elif job.stage == STAGES[-1]:
                persist.set_document(conn, doc.id, status="ready")
    except InjectedCrash:
        raise  # a dead worker records nothing: the transaction rolled back, the job stays running
    except Exception as exc:
        code = f"{FAILURE_CLASS.get(job.stage, 'unknown')}:{type(exc).__name__}"
        retry = jobs.mark_failed(conn, job, code, ctx.max_attempts, ctx.backoff_s)
        log.warning("stage.failed", stage=job.stage, error=code, attempt=job.attempts, retry=retry)
        return True
    log.info(
        "stage.done", stage=job.stage, document_id=job.document_id, attempt=job.attempts,
        duration_ms=round((time.monotonic() - started) * 1000),
    )  # fmt: skip
    if hooks.after_stage:
        hooks.after_stage(job.stage)
    return True


def run_until_idle(conn: psycopg.Connection, ctx: RunContext, *, max_jobs: int = 1000) -> int:
    """Recover dead workers' jobs, then run jobs until none is left. A failed stage waiting out its
    backoff is waited for, not abandoned. Returns the number of job runs."""
    jobs.recover(conn, ctx.lease_s)
    count = 0
    while count < max_jobs:
        if run_one(conn, ctx):
            count += 1
            continue
        wait = _backoff_wait(conn)
        if wait is None:
            break
        time.sleep(wait)
    return count


def _backoff_wait(conn: psycopg.Connection) -> float | None:
    """Seconds until the earliest queued job of a still-processing document may run, or None."""
    row = conn.execute(
        "SELECT min(j.run_after) - now() FROM jobs j JOIN documents d ON d.id = j.document_id "
        "WHERE j.status = 'queued' AND d.status IN ('queued', 'processing') AND j.run_after > now()"
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return float(max(0.05, row[0].total_seconds()))
