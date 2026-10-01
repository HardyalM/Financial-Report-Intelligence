"""Topic and summary calls with validate, retry once, drop (RAG section 4.4, M5.2).

One provider call per topic (and one for the summary). The reply is parsed, validated by V1-V8, and
if any violation remains the call is repeated once with the violation list. Paragraphs that still
fail are dropped by `finalize`; a topic left with none is `validation_failed`. The retry never makes
a topic worse: if it yields fewer accepted paragraphs than the first pass, the first pass is kept.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from finintel.commentary.prompts import (
    QA_SYSTEM,
    SUMMARY_SYSTEM,
    SYSTEM,
    qa_user,
    retry_user,
    select_truth,
    summary_user,
    topic_user,
)
from finintel.commentary.render import TruthEntry
from finintel.commentary.validators import (
    TopicReport,
    Violation,
    feedback,
    finalize,
    summary_evidence,
    validate_output,
)
from finintel.commentary.validators.validate import SUMMARY_SCHEMA
from finintel.contracts.commentary import Paragraph
from finintel.llm import LLMProvider
from finintel.llm.anthropic_provider import LLMError
from finintel.narrative.models import Chunk

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


@dataclass
class CallResult:
    status: str  # "ok" | "insufficient_evidence" | "validation_failed"
    reason: str | None
    paragraphs: list[Paragraph]
    retried: bool
    first_pass: Counter[str]  # violation codes before the retry: the pre-validation metrics
    final_violations: list[Violation] = field(default_factory=list)


def parse_reply(reply: str) -> Any | None:
    try:
        return json.loads(_FENCE.sub("", reply.strip()))
    except ValueError:
        return None


Validate = Callable[[Any], TopicReport]


def _call(provider: LLMProvider, system: str, user: str, validate: Validate) -> CallResult:
    reply = provider.complete(system, user)
    first = _validate(reply, validate)
    counts = Counter(v.code for v in first.violations)
    if not first.needs_retry:
        status, reason, paragraphs = finalize(first, retried=False)
        return CallResult(status, reason, paragraphs, False, counts, first.violations)
    try:
        retry_reply = provider.complete(system, retry_user(user, reply, feedback(first)))
    except LLMError as exc:
        if exc.code != "prompt_too_long":
            raise
        # The retry prompt (original + previous output + violations) does not fit this model's
        # context. No retry happens: drop what failed, keep what passed.
        status, reason, paragraphs = finalize(first, retried=False)
        return CallResult(status, reason, paragraphs, False, counts, first.violations)
    second = _validate(retry_reply, validate)
    first_kept = sum(p.accepted for p in first.paragraphs)
    second_kept = sum(p.accepted for p in second.paragraphs)
    chosen = second if second_kept >= first_kept else first
    status, reason, paragraphs = finalize(chosen, retried=True)
    return CallResult(status, reason, paragraphs, True, counts, chosen.violations)


def _validate(reply: str, validate: Validate) -> TopicReport:
    raw = parse_reply(reply)
    if raw is None:
        return TopicReport("?", "ok", None, [], [Violation("V1", "reply is not valid JSON")])
    return validate(raw)


def generate_topic(
    provider: LLMProvider,
    topic: str,
    chunks: Sequence[Chunk],
    truth: Mapping[str, TruthEntry],
    *,
    allowed_years: Collection[str],
    page_labels: Mapping[int, str] | None = None,
) -> CallResult:
    scoped = select_truth(truth, topic)
    evidence = {c.chunk_id: c for c in chunks}

    def validate(raw: Any) -> TopicReport:
        return validate_output(
            raw, topic=topic, evidence=evidence, truth=scoped,
            allowed_years=allowed_years, page_labels=page_labels,
        )  # fmt: skip

    return _call(provider, SYSTEM, topic_user(topic, scoped, chunks), validate)


def generate_summary(
    provider: LLMProvider,
    validated: Sequence[tuple[str, Paragraph]],
    evidence: Mapping[str, Chunk],
    truth: Mapping[str, TruthEntry],
    *,
    allowed_years: Collection[str],
    page_labels: Mapping[int, str] | None = None,
) -> CallResult:
    """Executive summary from validated paragraphs only. Citations may use only chunks those
    paragraphs cited (T14); the bullets pass the same V1-V8 (T16)."""
    pool = summary_evidence([p for _, p in validated], evidence)
    scoped: dict[str, TruthEntry] = {}
    for topic in {t for t, _ in validated}:
        scoped.update(select_truth(truth, topic))
    ordered = sorted(pool.values(), key=lambda c: c.char_start)
    user = summary_user([(t, p.template) for t, p in validated], scoped, ordered)

    def validate(raw: Any) -> TopicReport:
        return validate_output(
            raw, topic="executive_summary", evidence=pool, truth=scoped,
            allowed_years=allowed_years, page_labels=page_labels, schema=SUMMARY_SCHEMA,
        )  # fmt: skip

    return _call(provider, SUMMARY_SYSTEM, user, validate)


def generate_answer(
    provider: LLMProvider,
    question: str,
    chunks: Sequence[Chunk],
    truth: Mapping[str, TruthEntry],
    *,
    allowed_years: Collection[str],
    page_labels: Mapping[int, str] | None = None,
) -> CallResult:
    """Eval-only: one question through the same prompt rules and validators (EVAL 3.4)."""
    evidence = {c.chunk_id: c for c in chunks}

    def validate(raw: Any) -> TopicReport:
        return validate_output(
            raw, topic="qa", evidence=evidence, truth=truth,
            allowed_years=allowed_years, page_labels=page_labels,
        )  # fmt: skip

    return _call(provider, QA_SYSTEM, qa_user(question, truth, chunks), validate)
