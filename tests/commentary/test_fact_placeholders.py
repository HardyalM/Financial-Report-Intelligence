"""Supplemental facts as placeholders: rendered by code, named by their sentence, scored by value."""

from __future__ import annotations

from finintel.commentary.generate import answer_numeric
from finintel.commentary.qa import Answer, score_qa
from finintel.commentary.render import build_ground_truth
from finintel.commentary.validators import mismatched_placeholders as bad
from finintel.facts import SupplementalFact, SupplementalFacts
from finintel.facts.models import Source
from finintel.ratios import compute_ratios
from tests.commentary.builders import company_pack


def fact(id_: str, value: float | None, scale: int, *, per_share: bool = False, apm: bool = False,
         page: int = 43, pages: tuple[int, ...] = (43, 49)) -> SupplementalFact:  # fmt: skip
    return SupplementalFact(
        id=id_, label=id_, entity="group", period_id="FY2024", value=value, unit_scale=scale,
        currency="EUR", per_share=per_share, is_apm=apm, page=page, raw_text="x", confidence=0.95,
        sources=tuple(Source(page=p, raw_text="x", row_text="row") for p in pages),
    )  # fmt: skip


FACTS = SupplementalFacts(
    facts=(
        fact("basic_eps", 2.3, 1, per_share=True, page=141, pages=(141, 162)),
        fact("free_cash_flow", 6932.0, 1_000_000, apm=True),
        fact("underlying_operating_profit", 11179.0, 1_000_000, apm=True, pages=(47,)),
        fact("parent_investment_in_subsidiaries", None, 1_000_000, pages=(132, 197)),
    ),
    warnings=(),
)
PACK = company_pack()
TRUTH = build_ground_truth(PACK, compute_ratios(PACK), FACTS)


def test_facts_become_fact_placeholders_with_provenance_and_apm_note() -> None:
    eps = TRUTH["fact:basic_eps:FY2024"]
    assert (eps.rendered, eps.amount, eps.pages, eps.note) == ("€2.30", 2.3, (141, 162), None)
    fcf = TRUTH["fact:free_cash_flow:FY2024"]
    assert (fcf.rendered, fcf.amount, fcf.pages, fcf.note) == (
        "€6.9bn",
        6.932e9,
        (43, 49),
        "non-GAAP measure",
    )
    assert TRUTH["fact:underlying_operating_profit:FY2024"].rendered == "€11.2bn"
    # a conflicting fact is a null with its reason, never a number
    null = TRUTH["fact:parent_investment_in_subsidiaries:FY2024"]
    assert (
        null.rendered is None
        and null.reason == "conflicting_sources"
        and null.text().endswith("(sources disagree)")
    )


def test_items_carry_their_source_page_and_base_amount() -> None:
    revenue = TRUTH["item:revenue:FY2024"]
    assert revenue.pages == (141,) and revenue.amount == 60761.0 * 1_000_000


def test_a_fact_placeholder_must_be_named_and_qualifiers_are_not_interchangeable() -> None:
    assert bad("Free cash flow was {{fact:free_cash_flow:FY2024}}.") == []
    assert bad("Basic EPS was {{fact:basic_eps:FY2024}}.") == []
    assert bad("The year ended well at {{fact:free_cash_flow:FY2024}}.") != []
    # underlying operating profit is a different measure from the reported item
    assert bad("Underlying operating profit was {{item:operating_profit:FY2024}}.") != []
    assert bad("Operating profit was {{item:operating_profit:FY2024}}.") == []
    assert bad("Underlying operating profit was {{fact:underlying_operating_profit:FY2024}}.") == []
    assert (
        bad("Reported operating profit was {{item:operating_profit:FY2024}}, not underlying.") == []
    )
    # a segment figure needs both the segment and the measure named
    key = "{{fact:ice_cream_operating_profit:FY2024}}"
    assert bad(f"Ice Cream operating profit was {key}.") == []
    assert bad(f"Operating profit was {key}.") != [] and bad(f"Ice Cream was {key}.") != []


class Fixed:
    name = "fixed"

    def __init__(self, reply: str) -> None:
        self.reply = reply

    def complete(self, system: str, user: str) -> str:
        return self.reply


def test_a_numeric_answer_can_point_at_a_fact_but_never_state_it() -> None:
    scoped = {k: v for k, v in TRUTH.items() if k.endswith("FY2024")}
    status, para = answer_numeric(
        Fixed('{"status": "ok", "placeholder": "fact:free_cash_flow:FY2024"}'), "q", scoped
    )
    assert status == "ok" and para is not None and para.template == "{{fact:free_cash_flow:FY2024}}"
    assert para.rendered == "€6.9bn" and para.citations == []
    null_status, _ = answer_numeric(
        Fixed('{"status": "ok", "placeholder": "fact:parent_investment_in_subsidiaries:FY2024"}'),
        "q",
        scoped,
    )
    assert null_status == "validation_failed"  # a conflicting fact has no value to give
    assert (
        answer_numeric(
            Fixed('{"status": "ok", "placeholder": "fact:invented:FY2024"}'), "q", scoped
        )[0]
        == "validation_failed"
    )


def test_numeric_questions_are_scored_on_the_value_behind_the_fact() -> None:
    scoped = {k: v for k, v in TRUTH.items() if k.endswith("FY2024")}
    labs = {"page_basis": "pdf", "questions": [
        {"id": "n4", "kind": "numeric", "q": "?", "answer": 2.3, "unit": "EUR", "accept": [2.3]},
        {"id": "n5", "kind": "numeric", "q": "?", "answer": 6932, "unit": "EUR million", "accept": [6932, 6.9]},
        {"id": "t1", "kind": "trap", "q": "?", "answer": 9400, "unit": "EUR million", "not_answer": 11179},
    ]}  # fmt: skip
    answers = {}
    for qid, key in (("n4", "fact:basic_eps:FY2024"), ("n5", "fact:free_cash_flow:FY2024"),
                     ("t1", "fact:underlying_operating_profit:FY2024")):  # fmt: skip
        _, para = answer_numeric(
            Fixed('{"status": "ok", "placeholder": "' + key + '"}'), "q", scoped
        )
        answers[qid] = Answer("ok", [para] if para else [])
    r = score_qa(labs, answers, None, truth=TRUTH, unit_scale=1_000_000)
    assert r["failed"] == ["t1"]  # the underlying figure is the trap's wrong answer
