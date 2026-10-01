"""Assemble a Commentary: retrieve -> expand -> generate topics -> summary, or extractive.

`build_commentary` is the whole commentary stage for one document. Numbers come from the packs; the
model's text is validated; any provider failure falls back to extractive mode and says so.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from finintel.commentary.context import expand_context
from finintel.commentary.extractive import LABEL, extractive_paragraphs
from finintel.commentary.generate import CallResult, generate_summary, generate_topic
from finintel.commentary.prompts import PROMPT_VERSION, select_truth
from finintel.commentary.render import build_ground_truth
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
                context = expand_context([c.chunk_id for c in found.chunks], chunks)
                results[topic] = generate_topic(
                    provider, topic, context, truth, allowed_years=years, page_labels=page_labels
                )
                first_pass[topic] = results[topic].first_pass
            validated = [(t, p) for t, r in results.items() for p in r.paragraphs]
            if validated:
                summary = generate_summary(
                    provider, validated, by_id, truth, allowed_years=years, page_labels=page_labels
                )
                first_pass["executive_summary"] = summary.first_pass
        except LLMError as exc:
            use_model, fallback = False, exc.code
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
