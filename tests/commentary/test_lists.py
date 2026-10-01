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


def test_a_placeholder_must_be_named_by_its_own_sentence() -> None:
    from finintel.commentary.validators import mismatched_placeholders as bad

    v3 = "The Chief Executive said Unilever made solid progress in {{item:current_assets:FY2024}}."
    assert len(bad(v3)) == 1 and "current assets" in bad(v3)[0]
    assert bad("Current assets were {{item:current_assets:FY2024}}.") == []
    assert bad("Turnover was {{item:revenue:FY2024}}, {{change:item:revenue:FY2023:FY2024}}.") == []
    assert bad("Operating margin was {{ratio:operating_margin:FY2024}}.") == []
    assert bad("Debt to equity was {{ratio:debt_to_equity:FY2024}}.") == []
    # each sentence must name its own placeholder: naming it elsewhere does not help
    two = "Revenue grew. The figure was {{item:revenue:FY2024}}."
    assert len(bad(two)) == 1
    assert (
        bad("The year ended well {{ratio:ebitda_margin:FY2024}}.", known={"item:revenue:FY2024"})
        == []
    )


def test_the_guard_rejects_a_mislabelled_paragraph_in_the_pipeline() -> None:
    from finintel.commentary.validators import validate_output
    from tests.commentary.builders import Q_RISK, chunk, evidence, para, raw

    chunks = chunk(
        "c_a",
        "Management identifies supply chain disruption as a principal risk, noting "
        + Q_RISK
        + " across the group.",
    )
    text = "The Chief Executive said progress came to {{item:current_assets:FY2024}}."
    r = validate_output(
        raw([para(text, ("c_a", Q_RISK))]), topic="strategic_risks",
        evidence=evidence(chunks), truth=TRUTH,
    )  # fmt: skip
    assert {v.code for v in r.violations} == {"V9"} and r.needs_retry
    assert r.paragraphs[0].accepted is False


def test_going_concern_is_found_by_heading_and_needs_no_model() -> None:
    from finintel.commentary.lists import going_concern_bullets

    def gc(cid: str, page: int, heading: str, text: str, start: int) -> Chunk:
        c = chunk(cid, text, page=page, section="going_concern", char_start=start)
        return c.model_copy(update={"heading_path": ("Report", heading)})

    chunks = [
        gc(
            "g1",
            123,
            "GOING CONCERN",
            "The directors have prepared the accounts on the going concern basis for the period.",
            0,
        ),
        gc(
            "g2",
            145,
            "Going concern",
            "These financial statements have been prepared on a going concern basis today.",
            500,
        ),
        gc(
            "g3",
            128,
            "3. Going concern, viability and principal risks",
            "The auditor considered the going concern assessment of the directors carefully.",
            900,
        ),
    ]
    bullets = going_concern_bullets(["g1"], chunks, TRUTH)
    assert [b.citations[0].page for b in bullets] == [123, 145]  # the exact-heading passages only
    assert all(b.rendered.startswith("Going concern: “") for b in bullets)
    assert (
        going_concern_bullets(["x-not-retrieved"], chunks, TRUTH) == []
    )  # nothing retrieved: omitted
    assert going_concern_bullets(["g3"], [chunks[2]], TRUTH) == []  # no exact heading: omitted


def test_list_questions_are_answered_from_the_validated_bullets() -> None:
    from finintel.commentary.routing import list_answer

    retrieved = {"governance_and_directors": TopicResult(
        "governance_and_directors", "ok", (Retrieved("a0", 0.03, 0.9, 0.9, True),))}  # fmt: skip
    replies = good_replies()
    replies["governance_and_directors"] = [{
        "topic": "governance_and_directors", "status": "insufficient_evidence",
        "reason": "No evidence.", "paragraphs": []}]  # fmt: skip
    kam = build_commentary(
        provider=Scripted(replies), pack=PACK, ratios=RATIOS, chunks=KAM_CHUNKS, retrieved=retrieved
    ).commentary
    every = list_answer("What are the key audit matters?", kam)
    assert every is not None and len(every.paragraphs) == 3
    brazil = list_answer("What did the auditor say about the Brazil indirect tax matter?", kam)
    assert brazil is not None and len(brazil.paragraphs) == 1
    assert "Brazil" in brazil.paragraphs[0].rendered
    assert (
        list_answer("What did the auditor say about cyber?", kam) is None
    )  # nothing matches: model path
    assert list_answer("How does the company describe its strategy?", kam) is None


def test_list_bullets_must_cite_passages_in_order_of_appearance() -> None:
    from finintel.commentary.generate import generate_risk_list
    from finintel.commentary.validators import validate_output
    from finintel.commentary.validators.validate import LIST_SCHEMA

    chunks = risk_chunks()[:3]
    ev = {c.chunk_id: c for c in chunks}
    quotes = {
        c.chunk_id: f"Risk passage number {i} describes a distinct exposure"
        for i, c in enumerate(chunks)
    }

    def raw(order: list[str]) -> dict[str, Any]:
        return {"bullets": [
            {"template": f"Exposure {'abcdef'[n]}: described.", "citations": [{"chunk_id": cid, "quote": quotes[cid]}]}
            for n, cid in enumerate(order)]}  # fmt: skip

    def run(order: list[str]):  # type: ignore[no-untyped-def]
        return validate_output(
            raw(order),
            topic="strategic_risks",
            evidence=ev,
            truth={},
            schema=LIST_SCHEMA,
            ordered=True,
        )

    ok = run(["r0", "r1", "r2"])
    assert not ok.violations and all(p.accepted for p in ok.paragraphs)
    same = run(["r0", "r1", "r1"])  # two risks described in one passage is fine
    assert not same.violations
    bad = run(["r0", "r1", "r2", "r0"])  # the last bullet cites the overview passage again
    assert [v.code for v in bad.violations] == ["V10"] and bad.violations[0].paragraph == 3
    assert [p.accepted for p in bad.paragraphs] == [True, True, True, False] and bad.needs_retry
    unordered = validate_output(
        raw(["r2", "r0"]), topic="strategic_risks", evidence=ev, truth={}, schema=LIST_SCHEMA
    )  # without `ordered` nothing is checked
    assert not unordered.violations

    # through the generator: a violating first reply is retried with the feedback, then accepted
    good = raw(["r0", "r1", "r2"])
    first = raw(["r0", "r1", "r2", "r0"])
    p = Scripted({"strategic_risks": [first, good]})
    result = generate_risk_list(p, chunks, {}, allowed_years=())
    assert result.retried and len(result.paragraphs) == 3
    assert "V10 (paragraph 4)" in p.calls[1][1]
