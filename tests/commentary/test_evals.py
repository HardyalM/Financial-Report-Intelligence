"""E8 coverage, the 20-question scoring and ratings, on the tech lead's label shapes (offline)."""

from __future__ import annotations

import json
from typing import Any

from finintel.commentary.coverage import score_coverage
from finintel.commentary.qa import REQUIRED_MIX, Answer, mix_errors, score_qa
from finintel.commentary.ratings import score_ratings
from finintel.contracts.commentary import Commentary, Paragraph
from tests.commentary.builders import ROOT, company_pack, truth_for
from tests.commentary.scripted import Scripted, good_replies
from tests.commentary.test_generate import commentary

COMMENTARY: Commentary = commentary(Scripted(good_replies())).commentary
TRUTH = truth_for()
SCALE = company_pack()["unit_scale"]


def fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (ROOT / "fixtures" / "expected" / name).read_text(encoding="utf-8")
    )
    return data


def labels(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "page_basis": "1-indexed PDF viewer pages",
        "principal_risks": [
            {"name": "Supply chain disruption", "pages": [58]},
            {"name": "Cyber attack", "pages": [60]},
        ],
        "key_audit_matters": [{"name": "Impairment of goodwill (Group)", "pages": [131]}],
        "going_concern": {
            "conclusion": "Going concern basis adopted. No material uncertainty is identified.",
            "pages": [63],
        },
    }
    return {**base, **overrides}


def test_risk_recall_needs_the_name_on_or_near_a_listed_page() -> None:
    r = score_coverage(labels(), COMMENTARY, None)
    assert r["risks"]["found"] == 1 and r["risks"]["missing"] == ["Cyber attack"]
    assert r["risk_recall"] == 0.5 and r["kam_recall"] == 0.0
    far = labels(principal_risks=[{"name": "Supply chain", "pages": [80]}])
    assert score_coverage(far, COMMENTARY, None)["risk_recall"] == 0.0  # cited page 57
    several = labels(principal_risks=[{"name": "Supply chain", "pages": [80, 59]}])
    assert score_coverage(several, COMMENTARY, None)["risk_recall"] == 1.0  # any listed page


def test_a_name_is_covered_by_its_content_words_not_its_exact_spelling() -> None:
    near = labels(principal_risks=[{"name": "Disruption of supply chains (Group)", "pages": [57]}])
    assert score_coverage(near, COMMENTARY, None)["risk_recall"] == 1.0
    wrong = labels(principal_risks=[{"name": "Plastic packaging", "pages": [57]}])
    assert score_coverage(wrong, COMMENTARY, None)["risk_recall"] == 0.0


def test_printed_page_labels_are_converted_with_the_folio_offset() -> None:
    printed = labels(
        page_basis="printed page numbers", principal_risks=[{"name": "Supply chain", "pages": [54]}]
    )
    assert score_coverage(printed, COMMENTARY, 3)["risk_recall"] == 1.0


def test_going_concern_is_wrong_only_when_the_label_is_contradicted_outside_quotes() -> None:
    assert score_coverage(labels(), COMMENTARY, None)["going_concern_correct"] is True
    claimed = COMMENTARY.model_copy(deep=True)
    claimed.topics[2].paragraphs[
        0
    ].rendered += " There is a material uncertainty over going concern."
    r = score_coverage(labels(), claimed, None)
    assert r["going_concern_correct"] is False
    assert r["going_concern_claims_against_label"] == ["material uncertainty"]
    negated = COMMENTARY.model_copy(deep=True)
    negated.topics[2].paragraphs[0].rendered += " No material uncertainty was identified."
    assert score_coverage(labels(), negated, None)["going_concern_correct"] is True
    off_page = labels(going_concern={"conclusion": "x", "pages": [140]})
    assert score_coverage(off_page, COMMENTARY, None)["going_concern_correct"] is False


def test_the_tech_leads_label_files_have_the_required_mix_and_parse() -> None:
    qa = fixture("company_a.qa.json")
    assert mix_errors(qa) == [] and len(qa["questions"]) == 20 and sum(REQUIRED_MIX.values()) == 20
    coverage = fixture("company_a.coverage.json")
    assert len(coverage["principal_risks"]) == 14 and len(coverage["key_audit_matters"]) == 3
    score_coverage(coverage, COMMENTARY, None)  # accepts the real shape without raising
    score_qa(qa, {}, None, truth=TRUTH, unit_scale=SCALE)


def q(qid: str, kind: str, **fields: Any) -> dict[str, Any]:
    return {"id": qid, "kind": kind, "q": "?", **fields}


def para(template: str, quote: str = "", chunk_page: int | None = None) -> Paragraph:
    base = COMMENTARY.topics[0].paragraphs[0]
    cite = base.citations[0].model_copy(update={"quote": quote} if quote else {})
    if chunk_page is not None:
        cite = cite.model_copy(update={"page": chunk_page, "page_end": chunk_page})
    return base.model_copy(update={"template": template, "rendered": template, "citations": [cite]})


def test_numeric_answers_are_judged_on_the_value_behind_the_placeholder() -> None:
    rev = para("Turnover was {{item:revenue:FY2024}}.")
    op = para("Operating profit was {{item:operating_profit:FY2024}}.")
    labs = {"page_basis": "pdf", "questions": [
        q("n1", "numeric", answer=60761, unit="EUR million", accept=[60761, 60.761]),
        q("n2", "numeric", answer=9400, unit="EUR million", accept=[9400, 9.4]),
    ]}  # fmt: skip
    r = score_qa(
        labs,
        {"n1": Answer("ok", [rev]), "n2": Answer("ok", [rev])},
        None,
        truth=TRUTH,
        unit_scale=SCALE,
    )
    assert r["passed"] == 1 and r["failed"] == ["n2"]  # right figure, wrong question
    both = score_qa(
        labs,
        {"n1": Answer("ok", [rev]), "n2": Answer("ok", [op])},
        None,
        truth=TRUTH,
        unit_scale=SCALE,
    )
    assert both["passed"] == 2


def test_a_figure_not_in_the_pack_must_be_a_verified_quotation() -> None:
    quote = "free cash flow was 6,932 million euros for the year under review"
    quoted = para('Free cash flow was "6,932 million euros" in 2024.', quote)
    bare = para("Free cash flow was large.", quote)
    labs = {"page_basis": "pdf", "questions": [
        q("n5", "numeric", answer=6932, unit="EUR million", accept=[6932, 6.9])]}  # fmt: skip
    assert (
        score_qa(labs, {"n5": Answer("ok", [quoted])}, None, truth=TRUTH, unit_scale=SCALE)[
            "passed"
        ]
        == 1
    )
    assert (
        score_qa(labs, {"n5": Answer("ok", [bare])}, None, truth=TRUTH, unit_scale=SCALE)["passed"]
        == 0
    )


def test_a_trap_fails_when_the_wrong_figure_is_stated() -> None:
    trap = {"page_basis": "pdf", "questions": [
        q("t1", "trap", answer=9400, unit="EUR million", not_answer=11179)]}  # fmt: skip
    quote = "underlying operating profit was 11,179 million euros in the year"
    right = para("Operating profit was {{item:operating_profit:FY2024}}.")
    wrong = para('Underlying operating profit was "11,179 million euros".', quote)
    mixed = para(
        'Operating profit was {{item:operating_profit:FY2024}}; "11,179 million euros" underlying.',
        quote,
    )

    def score(p: Paragraph) -> int:
        result = score_qa(trap, {"t1": Answer("ok", [p])}, None, truth=TRUTH, unit_scale=SCALE)
        return int(result["passed"])

    assert (score(right), score(wrong), score(mixed)) == (1, 0, 0)


def test_narrative_needs_every_must_mention_and_a_cited_expected_page() -> None:
    risk = COMMENTARY.topics[1].paragraphs[0]  # cites page 57: "supply chain", "single-source"
    labs = {"page_basis": "pdf", "questions": [
        q("v1", "narrative", must_mention=["supply chain", "single-source"], pages=[57]),
        q("v2", "narrative", must_mention=["supply chain", "cyber"], pages=[57]),  # a term missing
        q("v3", "narrative", must_mention=["supply chain"], pages=[90]),  # wrong page
    ]}  # fmt: skip
    r = score_qa(
        labs,
        {k: Answer("ok", [risk]) for k in ("v1", "v2", "v3")},
        None,
        truth=TRUTH,
        unit_scale=SCALE,
    )
    assert r["passed"] == 1 and r["failed"] == ["v2", "v3"]


def test_absent_questions_need_insufficient_evidence_and_unanswered_ones_fail() -> None:
    labs = {"page_basis": "pdf", "questions": [
        q("a1", "absent", expected="not_in_report"),
        q("a2", "absent", expected="not_in_report")]}  # fmt: skip
    answers = {"a1": Answer("insufficient_evidence", []), "a2": Answer("ok", [para("x")])}
    r = score_qa(labs, answers, None, truth=TRUTH, unit_scale=SCALE)
    assert r["passed"] == 1 and r["failed"] == ["a2"]
    assert score_qa(labs, {}, None, truth=TRUTH, unit_scale=SCALE)["passed"] == 0


def test_ratings_are_complete_only_when_every_displayed_paragraph_is_rated() -> None:
    ids = ["revenue_drivers:0", "strategic_risks:0"]
    assert score_ratings(fixture("ratings.json"), ids)["complete"] is False  # status not_rated
    assert score_ratings(None, ids)["complete"] is False
    rated = {"status": "rated", "items": [
        {"id": "revenue_drivers:0", "rating": "supported"},
        {"id": "strategic_risks:0", "rating": "supported"}]}  # fmt: skip
    r = score_ratings(rated, ids)
    assert (r["complete"], r["supported"], r["contradicted"]) == (True, 1.0, 0)
    partial = {**rated, "items": rated["items"][:1]}
    assert score_ratings(partial, ids)["complete"] is False
    assert score_ratings(partial, ids)["unrated"] == ["strategic_risks:0"]
    bad = {
        **rated,
        "items": [rated["items"][0], {"id": "strategic_risks:0", "rating": "contradicted"}],
    }
    r = score_ratings(bad, ids)
    assert r["contradicted"] == 1 and r["supported"] == 0.5


def test_the_tech_leads_faithful_and_cited_form_is_read_with_a_stated_rule() -> None:
    ids = ["a:0", "a:1", "a:2"]
    items = [
        {"paragraph_id": "a:0", "faithful": True, "cited": True, "notes": ""},
        {"paragraph_id": "a:1", "faithful": True, "cited": False, "notes": "page does not say it"},
        {"paragraph_id": "a:2", "faithful": False, "cited": False, "notes": ""},
    ]
    r = score_ratings({"status": "rated", "items": items}, ids)
    assert r["complete"] and r["total"] == 3 and r["supported"] == 1 / 3
    assert (
        r["unsupported"] == ["a:1", "a:2"] and r["contradicted"] == 0
    )  # never derived from booleans
    explicit = [*items[:2], {"id": "a:2", "rating": "contradicted"}]
    assert score_ratings({"status": "rated", "items": explicit}, ids)["contradicted"] == 1
    incomplete = score_ratings({"status": "rated", "items": items[:2]}, ids)
    assert incomplete["complete"] is False and incomplete["unrated"] == ["a:2"]
    assert score_ratings({"status": "rated", "items": [{"paragraph_id": "a:0"}]}, ids)["total"] == 0
