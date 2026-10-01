"""Liquidity and capital is built by code: pack figures with their own pages, the current ratio labelled
computed, and the report's underlying ROIC quoted. No model writes it; ROCE is not shown."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from finintel.commentary.lists import liquidity_bullets, roic_bullet
from finintel.commentary.render import build_ground_truth, render_exact
from finintel.ratios import compute_ratios
from tests.commentary.builders import ROOT, chunk, company_pack, truth_for

TRUTH = truth_for()
FIGURES = "{{exact:current_assets:FY2024}}"


def roic_chunks() -> list:  # type: ignore[type-arg]
    stated = chunk(
        "r1",
        "Underlying return on invested capital improved 190bps to 18.1% (2023: 16.2%). This reflected "
        "strong underlying operating profit growth driven by turnover growth.",
        page=16, section="financial_review", char_start=0,
    )  # fmt: skip
    defined = chunk(
        "r2",
        "Underlying return on invested capital (ROIC) is a measure of the return generated on capital "
        "invested by the Group. Underlying ROIC is calculated as underlying operating profit after tax "
        "divided by the annual average of goodwill, intangible assets and inventories.",
        page=49, section="narrative_other", char_start=1000,
    )  # fmt: skip
    pay = chunk(
        "r3", "Underlying return on invested capital (average) is a remuneration target of 30% weight here.",
        page=104, section="remuneration_report", char_start=2000,
    )  # fmt: skip
    return [stated, defined, pay]


def test_exact_rendering_is_the_printed_amount_in_its_own_unit() -> None:
    assert render_exact(19194.0, 1_000_000, "EUR") == "€19,194 million"
    assert render_exact(25234.0, 1_000_000, "EUR") == "€25,234 million"
    assert render_exact(907.5, 1_000, "GBP") == "£907.5 thousand"
    assert render_exact(950.0, 1, "USD") == "$950"
    assert TRUTH["exact:total_equity:FY2024"].rendered == "€22,555 million"
    assert TRUTH["exact:current_assets:FY2024"].pages == (143,)


def test_the_balance_sheet_bullets_state_the_printed_figures_and_cite_their_own_page() -> None:
    bullets = liquidity_bullets("FY2024", TRUTH, [])
    assert len(bullets) == 3 and not any(
        b.citations for b in bullets
    )  # nothing quoted, no narrative page
    first, ratio, equity = bullets
    assert first.rendered == (
        "Current assets were €19,194 million and current liabilities were €25,234 million "
        "on the consolidated balance sheet."
    )
    assert [(f.rendered, f.pages) for f in first.figures] == [
        ("€19,194 million", [143]),
        ("€25,234 million", [143]),
    ]
    assert ratio.rendered == (
        "Current ratio, computed in code from current assets and current liabilities (the ratio is "
        "not printed in the report): €19,194 million / €25,234 million = 0.76x."
    )
    assert (
        "computed" in ratio.rendered
        and ratio.figures[-1].placeholder == "ratio:current_ratio:FY2024"
    )
    assert all(f.pages == [143] for f in ratio.figures)  # the inputs' page, not 172 and not 11
    assert equity.rendered.startswith(
        "Total equity, including non-controlling interests, was €22,555 million"
    )
    assert equity.figures[0].pages == [143]
    text = " ".join(b.rendered for b in bullets)
    assert (
        "17.2" not in text
        and "ROCE" not in text
        and "return on capital employed" not in text.lower()
    )


def test_a_bullet_whose_figures_are_unavailable_is_omitted() -> None:
    pack = json.loads(json.dumps(company_pack()))
    for pv in pack["items"]["current_liabilities"]["values"]:
        pv["value"] = None
    truth = build_ground_truth(pack, compute_ratios(pack))
    shown = liquidity_bullets("FY2024", truth, [])
    assert len(shown) == 1 and shown[0].rendered.startswith(
        "Total equity"
    )  # no ratio from a null input
    bank = json.loads(json.dumps(company_pack()))
    bank["document_type"] = "bank"
    assert (
        liquidity_bullets("FY2024", build_ground_truth(bank, compute_ratios(bank)), []) != []
    )  # equity only
    assert liquidity_bullets("FY2099", TRUTH, []) == []  # a period the pack does not have


def test_roic_is_quoted_not_computed_with_each_quote_on_its_own_page() -> None:
    bullet = roic_bullet(roic_chunks(), TRUTH)
    assert bullet is not None
    assert [c.page for c in bullet.citations] == [16, 49]
    assert all(c.match == "exact" for c in bullet.citations)
    assert "18.1% (2023: 16.2%)" in bullet.rendered and "quoted, not computed" in bullet.rendered
    assert bullet.figures == []  # no pack figure: nothing is computed
    # a remuneration target is not the company's result, and no sentence means no bullet
    assert roic_bullet([roic_chunks()[2]], TRUTH) is None
    assert roic_bullet([], TRUTH) is None
    only_stated = roic_bullet(roic_chunks()[:1], TRUTH)
    assert only_stated is not None and len(only_stated.citations) == 1


def test_the_topic_has_no_roce_and_the_model_is_never_asked_to_write_it() -> None:
    from finintel.commentary.prompts import TOPIC_NUMBERS, select_truth

    assert TOPIC_NUMBERS["liquidity_and_capital"] == frozenset()
    assert select_truth(TRUTH, "liquidity_and_capital") == {}
    assert not any(k.startswith("exact:") for k in select_truth(TRUTH, "revenue_drivers"))


@pytest.mark.skipif(
    not (ROOT / "fixtures" / "pdfs" / "company_a.pdf").exists(), reason="fixture PDF absent"
)
def test_company_a_liquidity_matches_the_printed_report(tmp_path: Path) -> None:
    from finintel.cli.chunks_cmd import chunk_pdf

    pack = company_pack()
    truth = build_ground_truth(pack, compute_ratios(pack))
    _, _, chunks, _ = chunk_pdf("company_a", tmp_path / "cache")
    bullets = liquidity_bullets("FY2024", truth, chunks)
    assert len(bullets) == 4
    assert [b.figures[0].pages for b in bullets[:3]] == [[143], [143], [143]]
    roic = bullets[3]
    assert [c.page for c in roic.citations] == [16, 49]
    assert "improved 190bps to 18.1% (2023: 16.2%)" in roic.rendered
