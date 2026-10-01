"""Figures carry their own source pages; quoted text must be cited; a change after a direction word
shows its size (the ratings fix: a pack figure beside an unrelated quote is not 'cited')."""

from __future__ import annotations

import copy
import json

from finintel.commentary.audit import audit_commentary
from finintel.commentary.render import build_ground_truth, render_template
from finintel.commentary.validators import finalize, validate_output
from finintel.commentary.validators.text import unverified_quotes
from finintel.ratios import compute_ratios
from tests.commentary.builders import (
    Q_RISK,
    RISK,
    ROOT,
    chunk,
    company_pack,
    evidence,
    para,
    raw,
    truth_for,
)
from tests.commentary.scripted import Scripted, good_replies
from tests.commentary.test_generate import commentary

TRUTH = truth_for()
A = chunk("c_a", RISK)


def run(text: str, truth=TRUTH):  # type: ignore[no-untyped-def]
    return validate_output(
        raw([para(text, ("c_a", Q_RISK))]), topic="strategic_risks", evidence=evidence(A), truth=truth,
        allowed_years=("2024", "2023"),
    )  # fmt: skip


def test_placeholders_carry_the_pages_that_print_them() -> None:
    assert TRUTH["item:current_assets:FY2024"].pages == (
        143,
    )  # the balance sheet, not a narrative page
    assert TRUTH["ratio:current_ratio:FY2024"].pages == (143,)
    assert TRUTH["ratio:roce:FY2024"].pages == (
        141,
        143,
    )  # operating profit, total assets, liabilities
    assert TRUTH["change:ratio:roce:FY2023:FY2024"].pages == (141, 143)  # both periods, same pages
    assert TRUTH["change:item:revenue:FY2023:FY2024"].pages == (141,)
    assert TRUTH["item:total_debt:FY2024"].pages == ()  # null: nothing to cite, nothing shown


def test_a_paragraph_lists_each_figure_with_its_source_pages() -> None:
    r = run(
        "Current assets were {{item:current_assets:FY2024}} and the current ratio was {{ratio:current_ratio:FY2024}}."
    )
    assert not r.violations
    figures = r.paragraphs[0].figures
    assert [(f.placeholder, f.rendered, f.pages) for f in figures] == [
        ("item:current_assets:FY2024", "€19.2bn", [143]),
        ("ratio:current_ratio:FY2024", "0.76x", [143]),
    ]
    _, _, kept = finalize(r, retried=False)
    assert [f.placeholder for f in kept[0].figures] == [
        "item:current_assets:FY2024",
        "ratio:current_ratio:FY2024",
    ]
    repeated = run(
        "Current assets were {{item:current_assets:FY2024}}; current assets, again {{item:current_assets:FY2024}}."
    )
    assert len(repeated.paragraphs[0].figures) == 1  # once per placeholder


def test_a_figure_with_a_value_but_no_source_page_is_refused() -> None:
    pack = company_pack()
    pack = copy.deepcopy(pack)
    for pv in pack["items"]["current_assets"]["values"]:
        pv["page"] = None
    truth = build_ground_truth(pack, compute_ratios(pack))
    r = run("Current assets were {{item:current_assets:FY2024}}.", truth)
    assert "V12" in {v.code for v in r.violations} and r.needs_retry


def test_quoted_text_must_be_a_verified_quote() -> None:
    ok = run(f'Management said "{Q_RISK}" about suppliers.')
    assert not ok.violations
    part = run('Management said "single-source suppliers for key categories" about suppliers.')
    assert not part.violations  # a part of a verified quote is a quote of it
    bad = run(
        f'Management said "{Q_RISK}" and "the committee considered the SEC letter at length" too.'
    )
    assert [v.code for v in bad.violations] == ["V11"] and "committee" in bad.violations[0].detail
    scare = run('The group "transformed" its supply chain.')
    assert [v.code for v in scare.violations] == [
        "V11"
    ]  # quotation marks assert the report says it
    assert unverified_quotes('a "b" and “c d”', ["c d e"]) == ["b"]


def test_a_change_after_a_direction_word_shows_its_size_not_a_second_sign() -> None:
    t = TRUTH
    roce = "{{change:ratio:roce:FY2023:FY2024}}"
    assert render_template(f"ROCE fell by {roce}.", t) == "ROCE fell by 1.6 pp."
    assert (
        render_template(f"ROCE was {roce}.", t) == "ROCE was -1.6 pp."
    )  # no direction word: sign kept
    rev = "{{change:item:revenue:FY2023:FY2024}}"
    assert render_template(f"Revenue rose {rev}.", t) == "Revenue rose 1.9%."
    assert render_template(f"Revenue growth was {rev}.", t) == "Revenue growth was +1.9%."
    # a wrong direction word is still a V7 violation: only the size is unsigned
    wrong = run("Operating margin rose by {{change:ratio:operating_margin:FY2023:FY2024}}.")
    assert "V7" in {v.code for v in wrong.violations}


def test_the_audit_counts_unsourced_figures_and_unquoted_quotes() -> None:
    run_ = commentary(Scripted(good_replies()))
    c = run_.commentary.model_copy(deep=True)
    chunks = {
        x.chunk_id: x for x in __import__("tests.commentary.scripted", fromlist=["CHUNKS"]).CHUNKS
    }
    clean = audit_commentary(c, chunks, TRUTH, allowed_years=("2024", "2023"))
    assert (
        clean["displayed_figures_without_source"] == 0 and clean["displayed_unverified_quotes"] == 0
    )
    assert any(
        p.figures for t in c.topics for p in t.paragraphs
    )  # the revenue paragraph lists its figures
    c.topics[0].paragraphs[
        0
    ].figures = []  # a displayed figure list that does not match its template
    c.topics[1].paragraphs[0].template += ' They said "something never cited".'
    broken = audit_commentary(c, chunks, TRUTH, allowed_years=("2024", "2023"))
    assert (
        broken["displayed_figures_without_source"] == 1
        and broken["displayed_unverified_quotes"] == 1
    )


def test_the_commentary_schema_requires_figures() -> None:
    from jsonschema import Draft202012Validator

    schema = json.loads((ROOT / "schemas" / "commentary.schema.json").read_text(encoding="utf-8"))
    doc = commentary(Scripted(good_replies())).commentary.model_dump(mode="json")
    assert list(Draft202012Validator(schema).iter_errors(doc)) == []
    del doc["topics"][0]["paragraphs"][0]["figures"]
    assert list(Draft202012Validator(schema).iter_errors(doc))
    assert doc["schema_version"] == "1.1.0"
