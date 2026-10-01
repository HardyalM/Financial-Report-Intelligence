"""A scripted provider and a canned scenario for the generation tests. No network, no model."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from finintel.narrative.models import Chunk
from finintel.retrieval.pipeline import Retrieved, TopicResult
from tests.commentary.builders import Q_RISK, RISK, chunk

REV = chunk(
    "c_rev",
    "Turnover growth was driven by pricing in Beauty and Wellbeing and by volume in Nutrition "
    "across emerging markets during the year.",
    page=15, section="ceo_review", char_start=100,
)  # fmt: skip
Q_REV = "driven by pricing in Beauty and Wellbeing and by volume in Nutrition"
RISKC = chunk("c_risk", RISK, page=57, char_start=1000)
GOV = chunk(
    "c_gov",
    "The Directors have a reasonable expectation that the Group will continue in operation and "
    "meet its liabilities as they fall due over the viability period assessed.",
    page=63, section="viability_statement", char_start=3000,
)  # fmt: skip
Q_GOV = "reasonable expectation that the Group will continue in operation and meet its liabilities"
LIQ = chunk(
    "c_liq",
    "Liquidity risk is the risk that the Group will face difficulty meeting obligations "
    "associated with its financial liabilities as they fall due.",
    page=177, section="notes_other", char_start=5000,
)  # fmt: skip
Q_LIQ = "Liquidity risk is the risk that the Group will face difficulty meeting obligations"
CHUNKS: list[Chunk] = [REV, RISKC, GOV, LIQ]


def cite(chunk_id: str, quote: str) -> dict[str, str]:
    return {"chunk_id": chunk_id, "quote": quote}


def bullet(template: str, chunk_id: str, quote: str) -> dict[str, Any]:
    return {"template": template, "citations": [cite(chunk_id, quote)]}


GOOD: dict[str, dict[str, Any]] = {
    "revenue_drivers": {
        "topic": "revenue_drivers", "status": "ok", "reason": None,
        "paragraphs": [{
            "template": "Revenue was {{item:revenue:FY2024}}, "
            "{{change:item:revenue:FY2023:FY2024}} on the prior year, attributed to pricing.",
            "citations": [{"chunk_id": "c_rev", "quote": Q_REV}]}],
    },
    "strategic_risks": {
        "topic": "strategic_risks", "status": "ok", "reason": None,
        "paragraphs": [{
            "template": "Management flags supply chain disruption as a principal risk.",
            "citations": [{"chunk_id": "c_risk", "quote": Q_RISK}]}],
    },
    "governance_and_directors": {
        "topic": "governance_and_directors", "status": "ok", "reason": None,
        "paragraphs": [{
            "template": "The directors state they expect the group to remain a going concern.",
            "citations": [{"chunk_id": "c_gov", "quote": Q_GOV}]}],
    },
    "liquidity_and_capital": {
        "topic": "liquidity_and_capital", "status": "ok", "reason": None,
        "paragraphs": [{
            "template": "The report describes liquidity risk in its financial risk disclosures.",
            "citations": [{"chunk_id": "c_liq", "quote": Q_LIQ}]}],
    },
}  # fmt: skip
SUMMARY: dict[str, Any] = {
    "bullets": [
        bullet("Revenue was {{item:revenue:FY2024}}.", "c_rev", Q_REV),
        bullet("Supply chain disruption is a principal risk.", "c_risk", Q_RISK),
        bullet("Directors expect continuity.", "c_gov", Q_GOV),
    ]
}


def retrieved_all() -> dict[str, TopicResult]:
    pairs = {
        "revenue_drivers": "c_rev", "strategic_risks": "c_risk",
        "governance_and_directors": "c_gov", "liquidity_and_capital": "c_liq",
    }  # fmt: skip
    return {
        topic: TopicResult(topic, "ok", (Retrieved(cid, 0.03, 0.9, 0.9, False),))
        for topic, cid in pairs.items()
    }


class Scripted:
    """Replies per call, chosen by the topic id in the prompt. Records every call."""

    name = "scripted"
    model_id = "scripted-1"

    def __init__(self, replies: Mapping[str, Sequence[str | Mapping[str, Any]]]) -> None:
        self._replies = {k: list(v) for k, v in replies.items()}
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        key = "summary"
        if (m := re.search(r'<TOPIC id="([a-z_]+)"', user)) is not None:
            key = m.group(1)
        elif "<QUESTION>" in user:
            key = "qa"
        queue = self._replies[key]
        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        return reply if isinstance(reply, str) else json.dumps(reply)


def good_replies() -> dict[str, list[str | Mapping[str, Any]]]:
    return {**{k: [v] for k, v in GOOD.items()}, "summary": [SUMMARY]}
