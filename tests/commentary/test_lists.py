"""Evidence-driven lists, the numeric pack route and the evidence floor (offline)."""

from __future__ import annotations

import json
from typing import Any

from finintel.commentary.generate import answer_numeric
from finintel.commentary.lists import kam_bullets, kam_groups, risk_section
from finintel.commentary.run import build_commentary
from finintel.narrative.models import Chunk
from finintel.retrieval.embeddings import FakeEmbedder
from finintel.retrieval.lexical import Bm25, evidence_coverage
from finintel.retrieval.pipeline import InMemoryIndex, Retrieved, TopicResult
from tests.commentary.builders import chunk, truth_for
from tests.commentary.scripted import Scripted, good_replies
from tests.commentary.test_generate import PACK, RATIOS

TRUTH = truth_for()


def audit_chunk(cid: str, leaf: str, text: str, page: int, start: int) -> Chunk:
    c = chunk(cid, text, page=page, section="auditors_report", char_start=start)
    return c.model_copy(update={"heading_path": ("Auditor's report", leaf)})


KAM_CHUNKS = [
    audit_chunk("a0", "3. Going concern", "We considered the going concern basis for the group.", 128, 0),
    audit_chunk("a1", "4. Key audit matters", "The key audit matters are those of most significance.", 129, 100),
    audit_chunk("k1", "4.1 Revenue recognition – Rebates (Group)",
                "Certain discounts for goods sold are only finalised when amounts are known later.", 130, 200),
    audit_chunk("k1b", "4.1 Revenue recognition – Rebates (Group)",
                "Our response included testing the accrual for rebates at year end carefully.", 130, 300),
    audit_chunk("k2", "4.2 Indirect tax contingent liabilities in Brazil (Group)",
                "The Group is subject to a number of indirect tax assessments in Brazil today.", 131, 400),
    audit_chunk("k3", "4.3 Investments in subsidiaries (Parent) (continued)",
                "We do not consider the recoverability of these investments to be high risk.", 132, 500),
    audit_chunk("z", "5. Our ability to detect irregularities",
                "We design procedures to detect irregularities including fraud in the group.", 133, 600),
]  # fmt: skip


def test_key_audit_matters_come_from_the_numbered_headings_under_the_kam_heading() -> None:
    groups = kam_groups(KAM_CHUNKS)
    assert [t for t, _ in groups] == [
        "Revenue recognition – Rebates (Group)",
        "Indirect tax contingent liabilities in Brazil (Group)",
        "Investments in subsidiaries (Parent)",
    ]
    assert [len(g) for _, g in groups] == [2, 1, 1]
    assert (
        kam_groups([c for c in KAM_CHUNKS if c.chunk_id != "a1"]) == []
    )  # no KAM heading, no list


def test_one_bullet_per_matter_each_citing_its_own_page_and_only_if_the_report_was_retrieved() -> (
    None
):
    bullets = kam_bullets(["a0"], KAM_CHUNKS, TRUTH)
    assert [b.citations[0].page for b in bullets] == [130, 131, 132]
    assert bullets[0].rendered.startswith(
        "Key audit matter: Revenue recognition – Rebates (Group). “Certain"
    )
    assert all(len(b.citations) == 1 and b.citations[0].match == "exact" for b in bullets)
    assert kam_bullets(["not-the-audit-report"], KAM_CHUNKS, TRUTH) == []
    unrelated = [chunk("g", "x " * 20, section="viability_statement")]
    assert kam_bullets(["g"], unrelated + KAM_CHUNKS, TRUTH) == []


def risk_chunks() -> list[Chunk]:
    out = []
    for i, page in enumerate((55, 56, 57)):
        c = chunk(f"r{i}", f"Risk passage number {i} describes a distinct exposure of the group today.",
                  page=page, section="principal_risks", char_start=i * 100)  # fmt: skip
        out.append(c.model_copy(update={"heading_path": ("Strategic report", "Principal Risks")}))
    other = chunk(
        "o",
        "Unrelated viability text for the period assessed here.",
        page=63,
        section="viability_statement",
    )
    return [*out, other]


def test_the_risk_section_is_every_chunk_under_the_retrieved_risks_heading() -> None:
    chunks = risk_chunks()
    assert [c.chunk_id for c in risk_section(["r1"], chunks)] == ["r0", "r1", "r2"]
    assert risk_section(["o"], chunks) == []


def risk_reply(chunks: list[Chunk]) -> dict[str, Any]:
    quotes = ["Risk passage number 0 describes a distinct exposure", "Risk passage number 1 describes a distinct exposure",
              "Risk passage number 2 describes a distinct exposure"]  # fmt: skip
    return {"bullets": [
        {"template": f"Exposure {name}: described in the report.",
         "citations": [{"chunk_id": c.chunk_id, "quote": q}]}
        for name, c, q in zip(("alpha", "beta", "gamma"), chunks[:3], quotes, strict=True)
    ]}  # fmt: skip


def test_the_commentary_lists_one_bullet_per_risk_each_on_its_own_page() -> None:
    chunks = risk_chunks()
    replies = good_replies()
    replies["strategic_risks"] = [risk_reply(chunks)]
    retrieved = {
        "strategic_risks": TopicResult(
            "strategic_risks", "ok", (Retrieved("r1", 0.03, 0.9, 0.9, True),)
        )
    }
    p = Scripted(replies)
    run = build_commentary(provider=p, pack=PACK, ratios=RATIOS, chunks=chunks, retrieved=retrieved)
    topic = run.commentary.topics[0]
    assert topic.status == "ok" and [b.citations[0].page for b in topic.paragraphs] == [55, 56, 57]
    sent = p.calls[0][1]
    assert sent.count("<chunk ") == 3 and 'id="o"' not in sent  # the whole section, nothing else


def test_a_provider_with_a_small_context_skips_the_list_and_takes_the_ordinary_path() -> None:
    chunks = risk_chunks()

    class Small(Scripted):
        context_tokens = 900

    replies = good_replies()
    retrieved = {
        "strategic_risks": TopicResult(
            "strategic_risks", "ok", (Retrieved("r1", 0.03, 0.9, 0.9, True),)
        )
    }
    p = Small(
        {
            **replies,
            "strategic_risks": [
                json.dumps(
                    {
                        "topic": "strategic_risks",
                        "status": "insufficient_evidence",
                        "reason": "No.",
                        "paragraphs": [],
                    }
                )
            ],
        }
    )
    run = build_commentary(provider=p, pack=PACK, ratios=RATIOS, chunks=chunks, retrieved=retrieved)
    assert run.commentary.topics[0].status == "insufficient_evidence"


def test_the_governance_topic_gains_the_kam_bullets() -> None:
    retrieved = {"governance_and_directors": TopicResult(
        "governance_and_directors", "ok", (Retrieved("a0", 0.03, 0.9, 0.9, True),))}  # fmt: skip
    replies = good_replies()
    replies["governance_and_directors"] = [{
        "topic": "governance_and_directors", "status": "insufficient_evidence",
        "reason": "No evidence on this.", "paragraphs": []}]  # fmt: skip
    run = build_commentary(
        provider=Scripted(replies), pack=PACK, ratios=RATIOS, chunks=KAM_CHUNKS, retrieved=retrieved
    )
    topic = run.commentary.topics[0]
    assert topic.status == "ok" and len(topic.paragraphs) == 3
    extractive = build_commentary(
        provider=None, pack=PACK, ratios=RATIOS, chunks=KAM_CHUNKS, retrieved=retrieved
    )
    assert len(extractive.commentary.topics[0].paragraphs) >= 3


def test_numeric_questions_get_a_placeholder_never_a_figure() -> None:
    scoped = {
        k: v for k, v in TRUTH.items() if k.startswith(("item:", "ratio:")) and k.endswith("FY2024")
    }

    class Fixed:
        name = "fixed"

        def __init__(self, reply: str) -> None:
            self.reply = reply

        def complete(self, system: str, user: str) -> str:
            return self.reply

    ok = Fixed('{"status": "ok", "placeholder": "item:operating_profit:FY2024"}')
    status, para = answer_numeric(ok, "What was operating profit?", scoped)
    assert status == "ok" and para is not None
    assert para.template == "{{item:operating_profit:FY2024}}" and para.rendered == "€9.4bn"
    assert para.citations == []

    for reply, expected in (
        ('{"status": "insufficient_evidence", "placeholder": null}', "insufficient_evidence"),
        ('{"status": "ok", "placeholder": "item:free_cash_flow:FY2024"}', "validation_failed"),
        (
            '{"status": "ok", "placeholder": "change:item:revenue:FY2023:FY2024"}',
            "validation_failed",
        ),
        (
            '{"status": "ok", "placeholder": "item:total_debt:FY2024"}',
            "validation_failed",
        ),  # null in the pack
        ("60761", "validation_failed"),
    ):
        assert answer_numeric(Fixed(reply), "q", scoped)[0] == expected, reply


def test_evidence_coverage_scores_rare_missing_words_low() -> None:
    chunks = [
        chunk(
            "a",
            "The Group reported strong turnover growth and improved margins across brands.",
            char_start=0,
        ),
        chunk(
            "b",
            "The board reviewed liquidity risk and going concern at the year end.",
            char_start=100,
        ),
    ]
    index = InMemoryIndex(chunks, FakeEmbedder(8))
    assert index.coverage("turnover growth across brands") == 1.0
    assert (
        index.coverage("What was the CET1 ratio for turnover") < 0.7
    )  # CET1 is nowhere in the report
    assert index.coverage("") == 0.0
    assert evidence_coverage(Bm25(chunks), "zzzz qqqq") == 0.0
