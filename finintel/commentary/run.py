"""Assemble a Commentary: retrieve -> expand -> generate topics -> summary, or extractive.

`build_commentary` is the whole commentary stage for one document. Numbers come from the packs; the
model's text is validated; any provider failure falls back to extractive mode and says so.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from finintel.commentary.context import TOKEN_BUDGET, expand_context
from finintel.commentary.extractive import LABEL, extractive_paragraphs
from finintel.commentary.generate import (
    CallResult,
    generate_risk_list,
    generate_summary,
    generate_topic,
)
from finintel.commentary.lists import kam_bullets, risk_section
from finintel.commentary.prompts import PROMPT_VERSION, select_truth
from finintel.commentary.render import TruthEntry, build_ground_truth
from finintel.commentary.snapshot import numbers_snapshot
from finintel.contracts.commentary import (
    Commentary,
    CommentaryModel,
    Paragraph,
    Summary,
    Topic,
)
from finintel.contracts.ratio_pack import RatioPack
from finintel.llm import LLMProvider
from finintel.llm.anthropic_provider import LLMError
from finintel.narrative.models import Chunk
from finintel.retrieval.pipeline import TopicResult
from finintel.retrieval.queries import OPTIONAL_TOPICS, QUERY_SET_VERSION

SCHEMA_VERSION = "1.0.0"
DISCLAIMER = (
    "Research aid, not investment advice. Figures are extracted and computed by code from the "
    "filed accounts; narrative is quoted from the report with page references."
)
INSUFFICIENT = "The retrieved evidence did not clear the evidence floor for this topic."


@dataclass
class CommentaryRun:
    commentary: Commentary
    snapshot: dict[str, Any]
    metrics: dict[str, Any]
    fallback_reason: str | None = None
    first_pass: dict[str, Counter[str]] = field(default_factory=dict)


def sha256_json(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def retrieval_set_id(retrieved: Mapping[str, TopicResult]) -> str:
    rows = {
        topic: [[c.chunk_id, round(c.score, 6)] for c in result.chunks]
        for topic, result in sorted(retrieved.items())
    }
    return sha256_json(rows)


def allowed_years(pack: Mapping[str, Any]) -> set[str]:
    years: set[str] = set()
    for period in pack.get("periods", []):
        for text in (period.get("label"), period.get("end_date")):
            if text and len(text) >= 4 and text[:4].isdigit():
                years.add(text[:4])
    return years


def context_budget(provider: object) -> int:
    """Evidence tokens per call: the provider's own limit (a small local context) or the default."""
    return int(getattr(provider, "context_tokens", TOKEN_BUDGET))


LIST_MIN_BUDGET = 3000  # a provider with less context than this cannot take the whole section
LIST_MAX_TOKENS = 12_000
LIST_MIN_CHUNKS = 3  # a list over one passage is just a paragraph


def _risk_list(
    provider: LLMProvider,
    ids: Sequence[str],
    chunks: Sequence[Chunk],
    truth: Mapping[str, TruthEntry],
    years: Collection[str],
    page_labels: Mapping[int, str] | None,
) -> CallResult | None:
    """One bullet per principal risk, if the section was retrieved and the model can read it all."""
    if context_budget(provider) < LIST_MIN_BUDGET:
        return None
    section = risk_section(ids, chunks)
    if len(section) < LIST_MIN_CHUNKS or sum(c.token_count for c in section) > LIST_MAX_TOKENS:
        return None
    try:
        return generate_risk_list(
            provider, section, truth, allowed_years=years, page_labels=page_labels
        )
    except LLMError as exc:
        if exc.code != "prompt_too_long":
            raise
        return None


def _add_kams(
    result: CallResult,
    ids: Sequence[str],
    chunks: Sequence[Chunk],
    truth: Mapping[str, TruthEntry],
    page_labels: Mapping[int, str] | None,
) -> None:
    """Append one code-built bullet per key audit matter to the governance topic."""
    bullets = kam_bullets(ids, chunks, truth, page_labels)
    if bullets:
        result.paragraphs = [*result.paragraphs, *bullets]
        result.status = "ok"
        result.reason = None


def fitted_context[T](
    provider: object,
    selected: Sequence[str],
    chunks: Sequence[Chunk],
    call: Callable[[list[Chunk]], T],
) -> T:
    """Run `call` on the expanded context; if the provider says the prompt does not fit its
    context, shrink the evidence budget and try again, down to the single best chunk."""
    budget = context_budget(provider)
    while True:
        context = expand_context(selected, chunks, budget)
        try:
            return call(context)
        except LLMError as exc:
            if exc.code != "prompt_too_long" or len(context) <= 1:
                raise
            budget = int(budget * 0.7)


def build_commentary(
    *,
    provider: LLMProvider | None,
    pack: Mapping[str, Any],
    ratios: RatioPack,
    chunks: Sequence[Chunk],
    retrieved: Mapping[str, TopicResult],
    page_labels: Mapping[int, str] | None = None,
    query_set_version: str = QUERY_SET_VERSION,
) -> CommentaryRun:
    truth = build_ground_truth(pack, ratios)
    by_id = {c.chunk_id: c for c in chunks}
    years = allowed_years(pack)
    snapshot = numbers_snapshot(ratios, truth)
    fallback: str | None = None
    results: dict[str, CallResult] = {}
    summary: CallResult | None = None
    first_pass: dict[str, Counter[str]] = {}

    use_model = provider is not None
    if provider is not None:
        try:
            for topic, found in retrieved.items():
                if found.status != "ok":
                    continue

                def one(context: list[Chunk], topic: str = topic) -> CallResult:
                    return generate_topic(
                        provider,
                        topic,
                        context,
                        truth,
                        allowed_years=years,
                        page_labels=page_labels,
                    )

                ids = [c.chunk_id for c in found.chunks]
                listed = (
                    _risk_list(provider, ids, chunks, truth, years, page_labels)
                    if topic == "strategic_risks"
                    else None
                )
                if listed is not None and listed.paragraphs:
                    results[topic] = listed  # one bullet per principal risk, from the section
                else:
                    results[topic] = fitted_context(provider, ids, chunks, one)
                first_pass[topic] = results[topic].first_pass
                if topic == "governance_and_directors":
                    _add_kams(results[topic], ids, chunks, truth, page_labels)
            validated = [(t, p) for t, r in results.items() for p in r.paragraphs]
            if validated:
                try:
                    summary = generate_summary(
                        provider, validated, by_id, truth,
                        allowed_years=years, page_labels=page_labels,
                    )  # fmt: skip
                    first_pass["executive_summary"] = summary.first_pass
                except LLMError as exc:
                    if exc.code != "prompt_too_long":
                        raise
                    summary = None  # the summary prompt does not fit: no summary, topics stand
        except LLMError as exc:
            use_model, fallback = False, str(exc)
            results, summary, first_pass = {}, None, {}

    topics: list[Topic] = []
    for topic, found in retrieved.items():
        if found.status != "ok":
            status = "omitted" if topic in OPTIONAL_TOPICS else "insufficient_evidence"
            topics.append(
                Topic(
                    topic=topic,
                    status=status,
                    reason=None if status == "omitted" else INSUFFICIENT,
                    paragraphs=[],
                )
            )
        elif use_model:
            r = results[topic]
            topics.append(
                Topic(topic=topic, status=r.status, reason=r.reason, paragraphs=r.paragraphs)
            )
        else:
            paragraphs = extractive_paragraphs(
                topic,
                [c.chunk_id for c in found.chunks],
                by_id,
                select_truth(truth, topic),
                page_labels,
            )
            if topic == "governance_and_directors":
                paragraphs += kam_bullets(
                    [c.chunk_id for c in found.chunks], chunks, truth, page_labels
                )
            topics.append(
                Topic(
                    topic=topic,
                    status="ok" if paragraphs else "insufficient_evidence",
                    reason=None if paragraphs else "No passage could be quoted verbatim.",
                    paragraphs=paragraphs,
                )
            )
    bullets: list[Paragraph] = summary.paragraphs if summary else []
    if summary is not None:
        summary_status = "ok" if bullets else "validation_failed"
    else:
        summary_status = "omitted"
    model = (
        CommentaryModel(
            provider=provider.name, model_id=getattr(provider, "model_id", provider.name)
        )
        if use_model and provider is not None
        else None
    )
    commentary = Commentary(
        schema_version=SCHEMA_VERSION,
        mode="generated" if use_model else "extractive",
        label=None if use_model else LABEL,
        topics=topics,
        executive_summary=Summary(status=summary_status, bullets=bullets),
        model=model,
        prompt_version=PROMPT_VERSION if use_model else None,
        query_set_version=query_set_version,
        retrieval_set_id=retrieval_set_id(retrieved),
        trace_id=None,
        statement_pack_sha=ratios.statement_pack_sha,
        ratio_pack_sha=sha256_json(ratios.model_dump(mode="json")),
        disclaimer=DISCLAIMER,
    )
    metrics = pre_validation_metrics(first_pass)
    return CommentaryRun(commentary, snapshot, metrics, fallback, first_pass)


def pre_validation_metrics(first_pass: Mapping[str, Counter[str]]) -> dict[str, Any]:
    """Counts of what the model produced before validation (EVAL E4's pre-validation rates)."""
    total: Counter[str] = Counter()
    for counts in first_pass.values():
        total.update(counts)
    return {
        "calls": len(first_pass),
        "fabricated_or_out_of_set_quotes": total["V2"] + total["V3"],
        "naked_number_violations": total["V5"],
        "advice_violations": total["V6"],
        "direction_violations": total["V7"],
        "unknown_placeholders": total["V4"],
        "schema_violations": total["V1"],
        "paragraphs_without_citation": total["V8"],
    }
