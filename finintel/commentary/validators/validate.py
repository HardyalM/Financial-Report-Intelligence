"""Topic-level validation: V1 schema, V2 evidence set, V3 quotes, V4 placeholders, V5 numbers,
V6 advice, V7 direction, V8 at least one citation per paragraph."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator

from finintel.commentary.render import TruthEntry, placeholders, render_template
from finintel.commentary.validators.citations import QuoteError, build_citation
from finintel.commentary.validators.lexicon import advice_terms, direction_violations
from finintel.commentary.validators.numbers import naked_numbers, unit_beside_placeholder
from finintel.contracts.commentary import (
    Citation,
    Paragraph,
    ParagraphValidation,
    ParagraphValidationRemovedCitationsItem,
)
from finintel.narrative.models import Chunk

_CITATION = {
    "type": "object",
    "required": ["chunk_id", "quote"],
    "properties": {"chunk_id": {"type": "string"}, "quote": {"type": "string"}},
    # Extra fields (a model-supplied "page") are tolerated and never read: T3.
}
_PARAGRAPH = {
    "type": "object",
    "additionalProperties": False,
    "required": ["template", "citations"],
    "properties": {
        "template": {"type": "string", "minLength": 1},
        "citations": {"type": "array", "items": _CITATION},
    },
}
TOPIC_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["topic", "status", "reason", "paragraphs"],
    "properties": {
        "topic": {"type": "string"},
        "status": {"enum": ["ok", "insufficient_evidence"]},
        "reason": {"type": ["string", "null"]},
        "paragraphs": {"type": "array", "items": _PARAGRAPH},
    },
}
LIST_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["bullets"],
    "properties": {
        "bullets": {"type": "array", "minItems": 1, "maxItems": 20, "items": _PARAGRAPH}
    },
}
SUMMARY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["bullets"],
    "properties": {"bullets": {"type": "array", "minItems": 3, "maxItems": 5, "items": _PARAGRAPH}},
}


@dataclass(frozen=True)
class Violation:
    code: str  # "V1".."V8"
    detail: str
    paragraph: int | None = None


@dataclass
class ParagraphReport:
    index: int
    template: str
    rendered: str
    citations: list[Citation] = field(default_factory=list)
    removed: list[dict[str, str]] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return not self.violations and bool(self.citations)


@dataclass
class TopicReport:
    topic: str
    status: str  # "ok" | "insufficient_evidence"
    reason: str | None
    paragraphs: list[ParagraphReport]
    violations: list[Violation]  # everything found, including removed citations (V2, V3)

    @property
    def needs_retry(self) -> bool:
        return (
            any(v.code == "V1" for v in self.violations)
            or any(not p.accepted for p in self.paragraphs)
            or any(v.paragraph is None and v.code in {"V5", "V6"} for v in self.violations)
        )


def validate_output(
    raw: Any,
    *,
    topic: str,
    evidence: Mapping[str, Chunk],
    truth: Mapping[str, TruthEntry],
    allowed_years: Collection[str] = (),
    page_labels: Mapping[int, str] | None = None,
    schema: Mapping[str, Any] = TOPIC_SCHEMA,
) -> TopicReport:
    """One validation pass over a model's raw output (already parsed JSON)."""
    errors = sorted(Draft202012Validator(dict(schema)).iter_errors(raw), key=str)
    if errors:
        violations = [Violation("V1", e.message) for e in errors]
        return TopicReport(topic, "ok", None, [], violations)
    is_summary = "bullets" in raw
    status = "ok" if is_summary else raw["status"]
    if not is_summary and raw["topic"] != topic:
        return TopicReport(topic, "ok", None, [], [Violation("V1", f"topic is {raw['topic']!r}")])
    items: Sequence[Mapping[str, Any]] = raw["bullets" if is_summary else "paragraphs"]
    report = TopicReport(topic, status, None if is_summary else raw["reason"], [], [])
    if status == "ok" and not items:
        report.violations.append(Violation("V1", "status ok with no paragraphs"))
    if status == "insufficient_evidence":
        _check_reason(report, truth)
    counter = 0
    for index, item in enumerate(items):
        para = _check_paragraph(
            index, item, evidence, truth, allowed_years, page_labels or {}, counter
        )
        counter += len(para.citations)
        report.paragraphs.append(para)
        report.violations.extend(para.violations)
        report.violations.extend(
            Violation(r["code"], f"{r['chunk_id']}: {r['reason']}", index) for r in para.removed
        )
    return report


def _check_reason(report: TopicReport, truth: Mapping[str, TruthEntry]) -> None:
    reason = report.reason or ""
    if naked_numbers(reason, []) or placeholders(reason):
        report.violations.append(Violation("V5", "an insufficient_evidence reason states a number"))
    if advice_terms(reason, []):
        report.violations.append(Violation("V6", "advice language in the reason"))


def _check_paragraph(
    index: int,
    item: Mapping[str, Any],
    evidence: Mapping[str, Chunk],
    truth: Mapping[str, TruthEntry],
    allowed_years: Collection[str],
    page_labels: Mapping[int, str],
    counter: int,
) -> ParagraphReport:
    template: str = item["template"]
    para = ParagraphReport(index, template, render_template(template, truth))
    for given in item["citations"]:
        chunk = evidence.get(given["chunk_id"])
        if chunk is None:  # V2
            para.removed.append(
                {"code": "V2", "chunk_id": given["chunk_id"], "reason": "not_in_evidence_set"}
            )
            continue
        try:  # V3: the model's page, if any, is ignored; code derives it
            para.citations.append(
                build_citation(
                    chunk,
                    given["quote"],
                    f"cit_{counter + len(para.citations) + 1:02d}",
                    page_labels,
                )
            )
        except QuoteError as exc:
            para.removed.append({"code": "V3", "chunk_id": chunk.chunk_id, "reason": exc.code})
    quotes = [c.quote for c in para.citations]
    for key in placeholders(template):  # V4
        if key not in truth:
            para.violations.append(Violation("V4", f"unknown placeholder {{{{{key}}}}}", index))
    for beside in unit_beside_placeholder(template):  # V4: the placeholder already says it
        para.violations.append(Violation("V4", f"unit text beside a placeholder: {beside}", index))
    notes = {c.note_number for c in (evidence[x.chunk_id] for x in para.citations) if c.note_number}
    bad = naked_numbers(template, quotes, allowed_years=allowed_years, note_numbers=notes)
    if bad:  # V5
        para.violations.append(Violation("V5", f"naked numbers: {', '.join(bad)}", index))
    for term in advice_terms(template, quotes):  # V6
        para.violations.append(Violation("V6", f"advice language: {term}", index))
    for problem in direction_violations(template, quotes, truth):  # V7
        para.violations.append(Violation("V7", problem, index))
    if not para.citations:  # V8
        para.violations.append(Violation("V8", "no surviving citation", index))
    return para


def feedback(report: TopicReport) -> list[str]:
    """The violation list to feed back on the single retry."""
    lines = []
    for v in report.violations:
        where = "" if v.paragraph is None else f" (paragraph {v.paragraph + 1})"
        lines.append(f"{v.code}{where}: {v.detail}")
    return lines


def finalize(report: TopicReport, *, retried: bool) -> tuple[str, str | None, list[Paragraph]]:
    """Apply the drop policy. Returns (status, reason, paragraphs) for the persisted topic.

    Paragraphs that still violate are dropped. A topic left with none is `validation_failed`;
    an accepted `insufficient_evidence` carries no paragraphs and keeps its reason.
    """
    if report.status == "insufficient_evidence":
        clean = not any(v.code == "V1" or v.paragraph is None for v in report.violations)
        if clean:
            return "insufficient_evidence", report.reason, []
        return "validation_failed", None, []
    kept = [
        Paragraph(
            template=p.template,
            rendered=p.rendered,
            citations=p.citations,
            validation=ParagraphValidation(
                retried=retried,
                removed_citations=[
                    ParagraphValidationRemovedCitationsItem(
                        chunk_id=r["chunk_id"], reason=f"{r['code']}:{r['reason']}"
                    )
                    for r in p.removed
                ],
            ),
        )
        for p in report.paragraphs
        if p.accepted
    ]
    return ("ok", None, kept) if kept else ("validation_failed", None, [])


def summary_evidence(
    paragraphs: Sequence[Paragraph], evidence: Mapping[str, Chunk]
) -> dict[str, Chunk]:
    """Only the chunks cited by validated paragraphs: nothing new enters at the summary (T14)."""
    cited = {c.chunk_id for p in paragraphs for c in p.citations}
    return {cid: chunk for cid, chunk in evidence.items() if cid in cited}
