"""The 20-question set (EVAL 3.4): judge-free scoring of `generate_answer` outputs.

Label shape (the tech lead's): `{id, kind, q, ...}`; kind is numeric, narrative, absent or trap.

- numeric / trap: a figure is right when a displayed paragraph either uses an `item:` placeholder
  whose pack value, in the question's unit, equals `answer`, or quotes (verbatim, verified) a number
  in `accept` (or `answer`). It is wrong when it does either for `not_answer`. We compare the value
  behind the placeholder, never its rounded rendering.
- narrative: at least one verified citation on one of `pages`, and every `must_mention` term is in
  the displayed text or its quotes (case-insensitive, thousands separators ignored).
- absent: the answer is `insufficient_evidence` with no paragraphs.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from finintel.commentary.render import PLACEHOLDER, TruthEntry
from finintel.commentary.validators.text import blank_verified_quotes, verified_spans
from finintel.contracts.commentary import Paragraph
from finintel.evals.e3 import uses_printed_pages

REQUIRED_MIX = {"numeric": 6, "narrative": 8, "absent": 3, "trap": 3}
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_UNIT_WORDS = {"thousand": 1e3, "million": 1e6, "billion": 1e9}


@dataclass(frozen=True)
class Answer:
    status: str  # "ok" | "insufficient_evidence" | "validation_failed"
    paragraphs: Sequence[Paragraph]
    pages: tuple[int, ...] = ()  # source pages of a pack or fact answer (it cites no chunk)


def kind_of(question: Mapping[str, Any]) -> str:
    return str(question.get("kind") or question.get("type"))


def question_text(question: Mapping[str, Any]) -> str:
    return str(question.get("q") or question["question"])


def mix_errors(labels: Mapping[str, Any]) -> list[str]:
    counts: dict[str, int] = {}
    for q in labels["questions"]:
        counts[kind_of(q)] = counts.get(kind_of(q), 0) + 1
    return [
        f"{kind}: expected {n}, found {counts.get(kind, 0)}"
        for kind, n in REQUIRED_MIX.items()
        if counts.get(kind, 0) != n
    ] + [f"unknown kind {k}" for k in counts if k not in REQUIRED_MIX]


def _multiplier(unit: str) -> float:
    for word, factor in _UNIT_WORDS.items():
        if word in unit.lower():
            return factor
    return 1.0


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


def _quoted_numbers(para: Paragraph) -> list[float]:
    spans = verified_spans(para.template, [c.quote for c in para.citations])
    return [float(m.group(0).replace(",", "")) for s in spans for m in _NUMBER.finditer(s)]


def _placeholder_amounts(para: Paragraph, truth: Mapping[str, TruthEntry]) -> list[float]:
    """Money amounts (base currency units) of the item and fact placeholders a paragraph uses."""
    amounts = []
    for m in PLACEHOLDER.finditer(para.template):
        entry = truth.get(m.group(1))
        if m.group(1).startswith(("item:", "fact:")) and entry and entry.amount is not None:
            amounts.append(entry.amount)
    return amounts


def _states(
    paras: Sequence[Paragraph],
    amount: float,
    accept: Collection[float],
    unit: float,
    truth: Mapping[str, TruthEntry],
    unit_scale: int | None,
) -> bool:
    for p in paras:
        if any(_close(a, amount * unit) for a in _placeholder_amounts(p, truth)):
            return True
        if any(_close(n, v) for n in _quoted_numbers(p) for v in accept):
            return True
    return False


def _text(paras: Sequence[Paragraph]) -> str:
    body = [blank_verified_quotes(p.rendered, [c.quote for c in p.citations]) for p in paras]
    body += [c.quote for p in paras for c in p.citations]
    return " ".join(body).lower().replace(",", "")


def _check(
    q: Mapping[str, Any],
    answer: Answer,
    shift: int,
    truth: Mapping[str, TruthEntry],
    unit_scale: int | None,
) -> bool:
    paras = list(answer.paragraphs)
    shown = answer.status == "ok" and bool(paras)
    kind = kind_of(q)
    if kind == "absent":
        return answer.status == "insufficient_evidence" and not paras
    if kind == "narrative":
        pages = {int(p) + shift for p in q.get("pages", [])}
        cited = any(pages & set(range(c.page, c.page_end + 1)) for p in paras for c in p.citations)
        body = _text(paras)
        terms = [str(t).lower().replace(",", "") for t in q.get("must_mention", [])]
        return shown and (not pages or cited) and all(t in body for t in terms)
    unit = _multiplier(str(q.get("unit", "")))
    accept = [float(v) for v in q.get("accept", [q["answer"]])]
    right = shown and _states(paras, float(q["answer"]), accept, unit, truth, unit_scale)
    if "not_answer" in q:
        wrong_values = [float(q["not_answer"])]
        if shown and _states(paras, float(q["not_answer"]), wrong_values, unit, truth, unit_scale):
            return False
    return right


def score_qa(
    labels: Mapping[str, Any],
    answers: Mapping[str, Answer],
    folio_offset: int | None,
    *,
    truth: Mapping[str, TruthEntry],
    unit_scale: int | None,
) -> dict[str, Any]:
    shift = 0
    if uses_printed_pages(labels):
        if folio_offset is None:
            raise ValueError("labels use printed pages but the document has no folio offset")
        shift = folio_offset
    results: dict[str, bool] = {}
    for q in labels["questions"]:
        answer = answers.get(q["id"])
        results[q["id"]] = bool(answer and _check(q, answer, shift, truth, unit_scale))
    return {
        "total": len(results),
        "passed": sum(results.values()),
        "failed": sorted(i for i, ok in results.items() if not ok),
        "mix_errors": mix_errors(labels),
    }
