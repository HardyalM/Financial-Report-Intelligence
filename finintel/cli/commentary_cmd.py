"""`finintel commentary <company>`: the commentary stage end to end (M5.2).

    finintel commentary company_a                 local Ollama by default (FININTEL_PROVIDER picks
                                                  gemini or anthropic); if the model is
                                                  unreachable: extractive (exit 0, labelled)
    finintel commentary company_a --replay FILE   offline replay of a recorded run
Writes artifacts/commentary/{stem}.json and the e4/e8/qa sections of the eval report.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from finintel.cache import StageCache
from finintel.cli.chunks_cmd import chunk_pdf
from finintel.commentary.artifact import read_recording, write_artifact
from finintel.commentary.audit import audit_commentary, displayed_ids
from finintel.commentary.coverage import score_coverage
from finintel.commentary.generate import CallResult, answer_numeric, generate_answer
from finintel.commentary.qa import Answer, question_text, score_qa
from finintel.commentary.ratings import score_ratings
from finintel.commentary.render import build_ground_truth
from finintel.commentary.routing import list_answer
from finintel.commentary.run import CommentaryRun, allowed_years, build_commentary, fitted_context
from finintel.contracts.commentary import Commentary
from finintel.evals.e1 import write_report
from finintel.extract import extract_pack
from finintel.facts import extract_facts
from finintel.llm import LLMProvider
from finintel.llm.anthropic_provider import LLMError
from finintel.llm.providers import select_provider
from finintel.llm.recording import RecordingProvider, ReplayProvider
from finintel.locate import locate
from finintel.narrative.models import Chunk
from finintel.parse.cached import cached_text_layer
from finintel.ratios import compute_ratios
from finintel.retrieval.embeddings import Embedder, FakeEmbedder
from finintel.retrieval.local_models import BgeM3Embedder, MemoEmbedder
from finintel.retrieval.pipeline import (
    COVERAGE_FLOOR,
    FusionOrderReranker,
    InMemoryIndex,
    OverlapReranker,
    Reranker,
    retrieve_all,
    retrieve_topic,
)
from finintel.retrieval.queries import TopicQueries

ERROR_PASSES = 3
ERROR_COOLDOWN_S = 90.0

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
    facts = extract_facts(layer, pack)
    truth = build_ground_truth(pack, ratios, facts)
    offset = located.folio_offset
    labels = (
        {p: str(p - offset) for p in range(1, layer.page_count + 1)} if offset is not None else {}
    )
    embedder, reranker = _embedder(embedder_name, cache_dir)
    index = InMemoryIndex(chunks, embedder)
    retrieved = {r.topic: r for r in retrieve_all(located.profile.document_type, index, reranker)}

    base: LLMProvider | None = (
        ReplayProvider(read_recording(replay)) if replay is not None else select_provider(env)
    )
    recorder = RecordingProvider(base) if base is not None and replay is None else None
    provider: LLMProvider | None = recorder or base
    run = build_commentary(
        provider=provider, pack=pack, ratios=ratios, chunks=chunks,
        retrieved=retrieved, page_labels=labels, facts=facts,
    )  # fmt: skip
    by_id = {c.chunk_id: c for c in chunks}
    years = allowed_years(pack)
    report: dict[str, Any] = {
        "mode": run.commentary.mode,
        "commentary": {
            "mode": run.commentary.mode,
            "provider": run.commentary.model.provider if run.commentary.model else None,
            "model_id": run.commentary.model.model_id if run.commentary.model else None,
            "fallback_reason": run.fallback_reason,
        },
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
            answers, errors = _ask_all(
                provider, qa_labels, chunks, index, reranker, truth, years, labels, run.commentary
            )
            report["qa"] = {
                **score_qa(
                    qa_labels, answers, offset, truth=truth, unit_scale=pack.get("unit_scale")
                ),
                "answers": {
                    qid: {
                        "status": a.status,
                        "pages": sorted(
                            {c.page for p in a.paragraphs for c in p.citations} | set(a.pages)
                        ),
                        "text": [p.rendered for p in a.paragraphs],
                        "error": errors.get(qid),
                    }
                    for qid, a in answers.items()
                },
            }
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
        {
            "company": pdf.stem,
            "claims": claims,
            "supplemental_facts": facts.model_dump(mode="json"),
        },
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


def _fact_pages(paragraph: Any, scoped: Mapping[str, Any]) -> tuple[int, ...]:
    """The source pages of the pack or fact figure a numeric answer points at."""
    if paragraph is None:
        return ()
    key = paragraph.template.strip("{}")
    entry = scoped.get(key)
    return tuple(entry.pages) if entry is not None else ()


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
    commentary: Commentary,
) -> tuple[dict[str, Answer], dict[str, str]]:
    answers: dict[str, Answer] = {}
    errors: dict[str, str] = {}
    floors: list[str] = []
    latest = max((k.rsplit(":", 1)[-1] for k in truth if k.startswith("item:")), default="")
    scoped = {  # the latest period's items and ratios: what a lookup question can ask for
        k: v
        for k, v in truth.items()
        if k.startswith(("item:", "ratio:", "fact:")) and k.endswith(latest)
    }

    def ask(q: Mapping[str, Any]) -> None:
        text = question_text(q)
        listed = list_answer(text, commentary) if "answer" not in q else None
        if listed is not None:  # a list-shaped question: answered from the validated bullets
            answers[q["id"]] = listed
            errors.pop(q["id"], None)
            return
        if "answer" in q:  # a figure question: answered from the statement pack, placeholder only
            try:
                status, paragraph = answer_numeric(provider, text, scoped)
            except LLMError as exc:
                answers[q["id"]] = Answer("error", [])
                errors[q["id"]] = exc.code
                return
            sources = _fact_pages(paragraph, scoped)
            answers[q["id"]] = Answer(status, [paragraph] if paragraph else [], sources)
            errors.pop(q["id"], None)
            return
        if index.coverage(text) < COVERAGE_FLOOR:  # nothing to ground an answer: no model call
            answers[q["id"]] = Answer("insufficient_evidence", [])
            floors.append(q["id"])
            return
        topic = TopicQueries("adhoc", (text,), frozenset())
        found = retrieve_topic(topic, index, reranker)

        def one(context: list[Chunk], text: str = text) -> CallResult:
            return generate_answer(
                provider, text, context, scoped, allowed_years=years, page_labels=page_labels
            )

        try:
            out = fitted_context(provider, [c.chunk_id for c in found.chunks], chunks, one)
        except LLMError as exc:  # one failed question is a failed question, not a lost run
            answers[q["id"]] = Answer("error", [])
            errors[q["id"]] = exc.code
            return
        answers[q["id"]] = Answer(out.status, out.paragraphs)
        errors.pop(q["id"], None)

    for q in labels["questions"]:
        ask(q)
    # A question the provider never answered (an outage, not a wrong answer) gets more passes after
    # a cool-down. Answered questions are never re-asked, so a result is never shopped for.
    for _ in range(ERROR_PASSES):
        pending = [q for q in labels["questions"] if answers[q["id"]].status == "error"]
        if not pending:
            break
        time.sleep(ERROR_COOLDOWN_S)
        for q in pending:
            ask(q)
    errors.update({qid: "evidence_floor" for qid in floors})
    return answers, errors
