"""`finintel commentary <company>`: the commentary stage end to end (M5.2).

    finintel commentary company_a                 live model if ANTHROPIC_API_KEY is set, else
                                                  extractive (exit 0, labelled "extractive")
    finintel commentary company_a --replay FILE   offline replay of a recorded run
Writes artifacts/commentary/{stem}.json and the e4/e8/qa sections of the eval report.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from finintel.cache import StageCache
from finintel.cli.chunks_cmd import chunk_pdf
from finintel.commentary.artifact import read_recording, write_artifact
from finintel.commentary.audit import audit_commentary, displayed_ids
from finintel.commentary.context import expand_context
from finintel.commentary.coverage import score_coverage
from finintel.commentary.generate import generate_answer
from finintel.commentary.qa import Answer, question_text, score_qa
from finintel.commentary.ratings import score_ratings
from finintel.commentary.render import build_ground_truth
from finintel.commentary.run import CommentaryRun, allowed_years, build_commentary
from finintel.evals.e1 import write_report
from finintel.extract import extract_pack
from finintel.llm import LLMProvider
from finintel.llm.anthropic_provider import provider_from_env
from finintel.llm.recording import RecordingProvider, ReplayProvider
from finintel.locate import locate
from finintel.parse.cached import cached_text_layer
from finintel.ratios import compute_ratios
from finintel.retrieval.embeddings import Embedder, FakeEmbedder
from finintel.retrieval.local_models import BgeM3Embedder, MemoEmbedder
from finintel.retrieval.pipeline import (
    FusionOrderReranker,
    InMemoryIndex,
    OverlapReranker,
    Reranker,
    retrieve_all,
    retrieve_topic,
)
from finintel.retrieval.queries import TopicQueries

COVERAGE_FORMAT = (
    '{ "page_basis": "1-indexed PDF viewer pages",\n'
    '  "principal_risks": [ {"name": "...", "pages": [55]} ],\n'
    '  "key_audit_matters": [ {"name": "...", "pages": [124, 130]} ],\n'
    '  "going_concern": {"conclusion": "...", "pages": [123, 145]} }'
)
QA_FORMAT = (
    '{ "page_basis": "1-indexed PDF viewer pages", "questions": [\n'
    '  {"id": "n1", "kind": "numeric", "q": "...", "answer": 60761, "unit": "EUR million",\n'
    '   "accept": [60761, 60.761]},\n'
    '  {"id": "v1", "kind": "narrative", "q": "...", "must_mention": ["..."], "pages": [55]},\n'
    '  {"id": "a1", "kind": "absent", "q": "...", "expected": "not_in_report"},\n'
    '  {"id": "t1", "kind": "trap", "q": "...", "answer": 9400, "not_answer": 11179} ] }'
    "  // 6 numeric, 8 narrative, 3 absent, 3 trap"
)


def _embedder(name: str, cache_dir: Path) -> tuple[Embedder, Reranker]:
    if name == "bge-m3":
        return MemoEmbedder(BgeM3Embedder(), cache_dir / "embeddings"), FusionOrderReranker()
    return FakeEmbedder(), OverlapReranker()


def run_commentary(
    company: str,
    cache_dir: Path,
    artifacts: Path,
    env: Mapping[str, str],
    *,
    replay: Path | None = None,
    embedder_name: str = "bge-m3",
    fixtures: Path = Path("fixtures") / "expected",
) -> tuple[CommentaryRun, dict[str, Any], Path]:
    pdf, sha, chunks, _ = chunk_pdf(company, cache_dir)
    cache = StageCache(cache_dir)
    layer, _ = cached_text_layer(pdf, sha, cache)
    located = locate(layer)
    result = extract_pack(pdf, cache)
    if result.pack is None:
        raise RuntimeError(f"extraction blocked: {result.status}")
    pack = result.pack
    ratios = compute_ratios(pack)
    truth = build_ground_truth(pack, ratios)
    offset = located.folio_offset
    labels = (
        {p: str(p - offset) for p in range(1, layer.page_count + 1)} if offset is not None else {}
    )
    embedder, reranker = _embedder(embedder_name, cache_dir)
    index = InMemoryIndex(chunks, embedder)
    retrieved = {r.topic: r for r in retrieve_all(located.profile.document_type, index, reranker)}

    base: LLMProvider | None = (
        ReplayProvider(read_recording(replay)) if replay is not None else provider_from_env(env)
    )
    recorder = RecordingProvider(base) if base is not None and replay is None else None
    provider: LLMProvider | None = recorder or base
    run = build_commentary(
        provider=provider, pack=pack, ratios=ratios, chunks=chunks,
        retrieved=retrieved, page_labels=labels,
    )  # fmt: skip
    by_id = {c.chunk_id: c for c in chunks}
    years = allowed_years(pack)
    report: dict[str, Any] = {
        "mode": run.commentary.mode,
        "commentary": {"mode": run.commentary.mode, "fallback_reason": run.fallback_reason},
        "e4": {
            **audit_commentary(run.commentary, by_id, truth, allowed_years=years),
            "pre_validation": run.metrics,
        },
    }
    notes: list[str] = []
    if run.commentary.mode == "generated" and provider is not None:
        qa_labels = _label(fixtures / f"{pdf.stem}.qa.json")
        cov_labels = _label(fixtures / f"{pdf.stem}.coverage.json")
        if cov_labels is not None:
            report["e8"] = score_coverage(cov_labels, run.commentary, offset)
        else:
            notes.append(f"{pdf.stem}.coverage.json is missing; format:\n{COVERAGE_FORMAT}")
        if qa_labels is not None:
            report["qa"] = score_qa(
                qa_labels,
                _ask_all(provider, qa_labels, chunks, index, reranker, truth, years, labels),
                offset,
                truth=truth,
                unit_scale=pack.get("unit_scale"),
            )
        else:
            notes.append(f"{pdf.stem}.qa.json is missing; format:\n{QA_FORMAT}")
    claims = {cid: p.rendered for cid, p in displayed_ids(run.commentary)}
    if run.commentary.mode == "generated":
        report["ratings"] = score_ratings(_label(fixtures / "ratings.json"), list(claims))
        if not report["ratings"]["complete"]:
            notes.append(
                "ratings.json is not complete: rate each displayed paragraph id in the artefact's "
                '"claims" as supported | unsupported | contradicted'
            )
    out = write_artifact(
        artifacts / "commentary" / f"{pdf.stem}.json",
        run,
        recorder.recording() if recorder is not None else None,
        {"company": pdf.stem, "claims": claims},
    )
    target = artifacts / "eval" / "latest" / "report.json"
    full: dict[str, Any] = {}
    if target.is_file():
        previous = json.loads(target.read_text(encoding="utf-8"))
        full = previous if previous.get("company") == pdf.stem else {}
    full.update({"company": pdf.stem, **{k: v for k, v in report.items() if k != "mode"}})
    for stale in ("e8", "qa", "ratings"):  # a section this run did not produce is not carried over
        if stale not in report:
            full.pop(stale, None)
    write_report(full, target)
    report["notes"] = notes
    return run, report, out


def _label(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _ask_all(
    provider: LLMProvider,
    labels: Mapping[str, Any],
    chunks: Any,
    index: InMemoryIndex,
    reranker: Reranker,
    truth: Any,
    years: Any,
    page_labels: Mapping[int, str],
) -> dict[str, Answer]:
    answers: dict[str, Answer] = {}
    for q in labels["questions"]:
        text = question_text(q)
        topic = TopicQueries("adhoc", (text,), frozenset())
        found = retrieve_topic(topic, index, reranker)
        context = expand_context([c.chunk_id for c in found.chunks], chunks)
        out = generate_answer(
            provider, text, context, truth, allowed_years=years, page_labels=page_labels
        )
        answers[q["id"]] = Answer(out.status, out.paragraphs)
    return answers
