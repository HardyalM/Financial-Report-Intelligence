"""The worker end to end on the committed company_a excerpt (fake embedder, extractive commentary)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest

from finintel.cache import StageCache
from finintel.db import jobs
from finintel.extract import ExtractionResult, extract_pack
from finintel.parse.engines.azure_di_engine import AzureDiConfig, AzureDiEngine
from finintel.ratios import pack_sha256
from finintel.worker import stages
from finintel.worker.context import Hooks, InjectedCrash, RunContext
from finintel.worker.runner import run_one, run_until_idle, submit_pdf
from finintel.worker.stages import STAGES
from tests.worker.conftest import EXCERPT

pytestmark = pytest.mark.network


def job_rows(conn: psycopg.Connection, doc: int) -> dict[str, tuple[str, int]]:
    rows = conn.execute(
        "SELECT stage, status, attempts FROM jobs WHERE document_id = %s", (doc,)
    ).fetchall()
    return {s: (st, a) for s, st, a in rows}


def scalar(conn: psycopg.Connection, sql: str, *args: Any) -> Any:
    row = conn.execute(sql, args).fetchone()
    assert row is not None
    return row[0]


def test_a_report_runs_to_ready_and_stores_the_same_pack_the_file_pipeline_builds(
    conn: psycopg.Connection, ctx: RunContext, tmp_path: Path
) -> None:
    doc = submit_pdf(conn, ctx, EXCERPT)
    assert run_until_idle(conn, ctx) == len(STAGES)
    assert scalar(conn, "SELECT status FROM documents WHERE id = %s", doc) == "ready"
    assert all(v == ("done", 1) for v in job_rows(conn, doc).values())
    file_pack = extract_pack(EXCERPT, StageCache(tmp_path / "file-cache")).pack
    assert file_pack is not None
    assert scalar(
        conn, "SELECT pack_sha FROM statement_packs WHERE document_id = %s", doc
    ) == pack_sha256(file_pack)
    assert scalar(conn, "SELECT document_type FROM documents WHERE id = %s", doc) == "corporate"
    for table in ("statement_packs", "extraction_reports", "ratio_packs", "commentaries"):
        assert scalar(conn, f"SELECT count(*) FROM {table}") == 1, table
    out = scalar(conn, "SELECT output FROM commentaries WHERE document_id = %s", doc)
    assert out["mode"] == "extractive" and out["label"]
    assert scalar(conn, "SELECT stale FROM commentaries") is False
    assert scalar(conn, "SELECT storage_key FROM documents WHERE id = %s", doc).startswith(
        "sha256/"
    )


def test_the_same_file_is_the_same_document_and_nothing_runs_twice(
    conn: psycopg.Connection, ctx: RunContext
) -> None:
    first = submit_pdf(conn, ctx, EXCERPT)
    run_until_idle(conn, ctx)
    second = submit_pdf(conn, ctx, EXCERPT)
    assert first == second
    assert run_until_idle(conn, ctx) == 0
    assert scalar(conn, "SELECT count(*) FROM documents") == 1
    assert scalar(conn, "SELECT count(*) FROM jobs") == len(STAGES)
    assert scalar(conn, "SELECT count(*) FROM statement_packs") == 1


def counting(ctx: RunContext, executed: Counter[str], **hooks: Any) -> RunContext:
    ctx.hooks = Hooks(on_execute=lambda s: executed.update([s]), **hooks)
    return ctx


def test_a_worker_crash_after_a_stage_commits_resumes_without_rerunning_any_stage(
    conn: psycopg.Connection, ctx: RunContext
) -> None:
    executed: Counter[str] = Counter()

    def crash(stage: str) -> None:
        if stage == "extract":
            raise InjectedCrash(stage)

    doc = submit_pdf(conn, counting(ctx, executed, after_stage=crash), EXCERPT)
    with pytest.raises(InjectedCrash):
        run_until_idle(conn, ctx)
    assert job_rows(conn, doc)["extract"][0] == "done"  # it committed before the worker died
    assert scalar(conn, "SELECT status FROM documents WHERE id = %s", doc) == "processing"

    restarted = counting(ctx, executed)  # a new worker process: fresh hooks, same database
    run_until_idle(conn, restarted)
    assert scalar(conn, "SELECT status FROM documents WHERE id = %s", doc) == "ready"
    assert executed == Counter(dict.fromkeys(STAGES, 1))  # every stage executed exactly once
    assert scalar(conn, "SELECT count(*) FROM statement_packs") == 1


def test_a_crash_inside_a_stage_rolls_it_back_and_it_completes_once_after_restart(
    conn: psycopg.Connection, ctx: RunContext
) -> None:
    executed: Counter[str] = Counter()

    def crash(stage: str) -> None:
        if stage == "ratios":
            raise InjectedCrash(stage)

    doc = submit_pdf(conn, counting(ctx, executed, during_stage=crash), EXCERPT)
    with pytest.raises(InjectedCrash):
        run_until_idle(conn, ctx)
    assert job_rows(conn, doc)["ratios"] == ("running", 1)  # no done mark, outputs rolled back
    assert scalar(conn, "SELECT count(*) FROM ratio_packs") == 0

    run_until_idle(conn, counting(ctx, executed))  # lease 0: the dead worker's job is re-queued
    assert scalar(conn, "SELECT status FROM documents WHERE id = %s", doc) == "ready"
    assert job_rows(conn, doc)["ratios"] == ("done", 2)  # a second attempt, one completion
    assert all(executed[s] == 1 for s in STAGES if s != "ratios") and executed["ratios"] == 2
    assert scalar(conn, "SELECT count(*) FROM ratio_packs") == 1  # never two


def failing_azure() -> AzureDiEngine:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    config = AzureDiConfig(endpoint="https://example-di.test", key="k")
    return AzureDiEngine(config, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_an_azure_failure_completes_on_the_fallback_with_reduced_verification(
    conn: psycopg.Connection, ctx: RunContext
) -> None:
    ctx.engines, ctx.azure = "all", failing_azure()
    doc = submit_pdf(conn, ctx, EXCERPT)
    run_until_idle(conn, ctx)
    assert scalar(conn, "SELECT status FROM documents WHERE id = %s", doc) == "ready"
    report = scalar(conn, "SELECT report FROM extraction_reports WHERE document_id = %s", doc)
    assert report["reduced_verification"] is True
    assert "azure_di" in report["engine_skipped"]
    pack = scalar(conn, "SELECT pack FROM statement_packs WHERE document_id = %s", doc)
    assert "reduced_verification" in {w["code"] for w in pack["warnings"]}


def test_a_failing_stage_retries_with_backoff_then_fails_with_a_classified_code(
    conn: psycopg.Connection, ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def boom(*args: Any) -> Any:
        calls.append(1)
        raise ValueError("sign flipped")

    monkeypatch.setitem(stages.STAGE_FUNCS, "ratios", boom)
    doc = submit_pdf(conn, ctx, EXCERPT)
    run_until_idle(conn, ctx)
    assert len(calls) == ctx.max_attempts
    assert job_rows(conn, doc)["ratios"] == ("failed", 3)
    assert scalar(conn, "SELECT status FROM documents WHERE id = %s", doc) == "failed"
    assert scalar(conn, "SELECT error_code FROM jobs WHERE stage = 'ratios'") == "map:ValueError"
    assert job_rows(conn, doc)["index"][0] == "queued"  # later stages never started


def test_a_unit_that_needs_confirmation_blocks_the_pipeline(
    conn: psycopg.Connection, ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocked = ExtractionResult(status="needs_unit_confirmation", pack=None, report={}, warnings=[])
    monkeypatch.setattr(stages, "extract_pack", lambda *a, **k: blocked)
    doc = submit_pdf(conn, ctx, EXCERPT)
    run_until_idle(conn, ctx)
    assert (
        scalar(conn, "SELECT status FROM documents WHERE id = %s", doc) == "needs_unit_confirmation"
    )
    states = job_rows(conn, doc)
    assert states["extract"][0] == "done" and states["ratios"][0] == "queued"
    assert run_until_idle(conn, ctx) == 0  # nothing runs until a person acts


def test_two_workers_never_claim_the_same_job(conn: psycopg.Connection, ctx: RunContext) -> None:
    submit_pdf(conn, ctx, EXCERPT)
    first = jobs.claim(conn)
    second = jobs.claim(conn)  # the first stage is running, so the next stage is not runnable yet
    assert first is not None and first.stage == "ingest" and second is None
    assert run_one(conn, ctx) is False  # also nothing for a worker that finds only a running stage
