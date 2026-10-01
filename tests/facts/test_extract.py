"""Supplemental facts: rows read by label, columns by header alignment, units from the header."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from finintel.facts import SPECS, SupplementalFacts, extract_facts
from finintel.facts.extract import parse_number, period_year
from tests.facts.builders import PACK, layer, period_table


def facts(tmp_path: Path, *pages: list) -> SupplementalFacts:  # type: ignore[type-arg]
    return extract_facts(layer(tmp_path, pages), PACK)


def one(result: SupplementalFacts, fact: str, period: str):  # type: ignore[no-untyped-def]
    return result.get(fact, period)


def test_a_row_is_read_under_its_period_header_with_the_unit_from_the_header(
    tmp_path: Path,
) -> None:
    r = facts(tmp_path, period_table("Free cash flow*", "6,932", "7,091"))
    now, before = one(r, "free_cash_flow", "FY2024"), one(r, "free_cash_flow", "FY2023")
    assert now is not None and before is not None
    assert (now.value, now.unit_scale, now.currency, now.page, now.raw_text) == (
        6932.0,
        1_000_000,
        "GBP",
        1,
        "6,932",
    )
    assert before.value == 7091.0 and now.is_apm and now.confidence == 0.9


def test_per_share_figures_ignore_the_million_in_the_header(tmp_path: Path) -> None:
    r = facts(tmp_path, period_table("Basic earnings per share (£)", "2.30", "2.58"))
    eps = one(r, "basic_eps", "FY2024")
    assert eps is not None and (eps.value, eps.unit_scale, eps.per_share, eps.is_apm) == (
        2.3,
        1,
        True,
        False,
    )
    assert eps.currency == "GBP"


def test_a_note_reference_column_is_not_a_figure(tmp_path: Path) -> None:
    r = facts(tmp_path, period_table("Investments in subsidiaries", "88,035", "88,000", note="4"))
    f = one(r, "parent_investment_in_subsidiaries", "FY2024")
    assert f is not None and f.value == 88035.0 and f.entity == "parent"


def test_a_re_presented_header_cell_covers_its_figure(tmp_path: Path) -> None:
    r = facts(tmp_path, period_table("Investments in subsidiaries", "88,035", "88,000", tag=True))
    f = one(r, "parent_investment_in_subsidiaries", "FY2023")
    assert f is not None and f.value == 88000.0


def test_no_header_or_no_unit_means_no_fact_and_a_warning(tmp_path: Path) -> None:
    no_unit = facts(tmp_path, period_table("Free cash flow", "6,932", "7,091", unit=False))
    assert no_unit.get("free_cash_flow", "FY2024") is None
    assert any(w.code == "not_found" and w.fact == "free_cash_flow" for w in no_unit.warnings)
    headless = [[(100.0, [("Free cash flow", 50, "l"), ("6,932", 380, "r"), ("7,091", 460, "r")])]]
    assert facts(tmp_path, *headless).get("free_cash_flow", "FY2024") is None


def test_a_label_must_match_whole_so_before_tax_is_not_the_figure(tmp_path: Path) -> None:
    r = facts(tmp_path, period_table("Underlying operating profit before tax", "11,179", "9,931"))
    assert r.get("underlying_operating_profit", "FY2024") is None


def test_pages_that_agree_within_printed_rounding_raise_confidence(tmp_path: Path) -> None:
    rounded = [(100.0, [("Free cash flow", 50, "l"), ("£6.9bn", 380, "r"), ("£7.1bn", 460, "r")]),
               (88.0, [("2024", 380, "r"), ("2023", 460, "r")])]  # fmt: skip
    r = facts(tmp_path, period_table("Free cash flow", "6,932", "7,091"), rounded)
    f = one(r, "free_cash_flow", "FY2024")
    assert (
        f is not None and f.value == 6932.0 and f.confidence == 0.95
    )  # the more precise source wins
    assert sorted(s.page for s in f.sources) == [1, 2]


def test_pages_that_disagree_give_a_null_and_a_warning(tmp_path: Path) -> None:
    r = facts(
        tmp_path,
        period_table("Free cash flow", "6,932", "7,091"),
        period_table("Free cash flow", "6,100", "7,091"),
    )
    f = one(r, "free_cash_flow", "FY2024")
    assert f is not None and f.value is None and f.page is None and f.note
    before = one(r, "free_cash_flow", "FY2023")
    assert before is not None and before.value == 7091.0
    conflicts = [(w.code, w.fact, w.pages) for w in r.warnings if w.code == "conflict"]
    assert conflicts == [("conflict", "free_cash_flow", (1, 2))]


def test_a_period_outside_the_pack_is_ignored(tmp_path: Path) -> None:
    extra = period_table("Free cash flow", "6,932", "7,091")
    r = extract_facts(layer(tmp_path, [extra]), {"periods": [{"id": "FY2024", "label": "2024"}]})
    assert [f.period_id for f in r.facts] == ["FY2024"]


def segment_page(ice_2024: str, other_2024: str) -> list:  # type: ignore[type-arg]
    cols = [("Beauty", 340), ("Home Care", 420), ("Ice Cream", 500), ("Total", 560)]
    rows: list = [(100.0, [("£ million", x, "r") for _, x in cols])]  # type: ignore[type-arg]
    rows.append((112.0, [(name, x, "r") for name, x in cols]))
    rows.append((130.0, [("2024", 50, "l")]))
    rows.append(
        (
            142.0,
            [
                ("Operating profit", 50, "l"),
                ("3", 300, "r"),
                (other_2024, 340, "r"),
                ("1,521", 420, "r"),
                (ice_2024, 500, "r"),
                ("9,400", 560, "r"),
            ],
        )
    )
    rows.append((190.0, [("2023", 50, "l")]))
    rows.append(
        (
            202.0,
            [
                ("Operating profit", 50, "l"),
                ("3", 300, "r"),
                ("2,209", 340, "r"),
                ("1,419", 420, "r"),
                ("760", 500, "r"),
                ("9,758", 560, "r"),
            ],
        )
    )
    return rows


def test_a_segment_cell_is_read_by_column_label_and_block_period(tmp_path: Path) -> None:
    r = facts(tmp_path, segment_page("571", "1,970"))
    now, before = (
        one(r, "ice_cream_operating_profit", "FY2024"),
        one(r, "ice_cream_operating_profit", "FY2023"),
    )
    assert now is not None and before is not None
    assert (now.value, now.unit_scale, now.entity, now.is_apm) == (
        571.0,
        1_000_000,
        "segment:Ice Cream",
        False,
    )
    assert before.value == 760.0  # the 2023 block, not 2024


def test_a_segment_row_with_no_column_label_is_not_read(tmp_path: Path) -> None:
    page = segment_page("571", "1,970")
    page = [row for row in page if row[0] != 112.0]  # the header row naming the columns is gone
    assert facts(tmp_path, page).get("ice_cream_operating_profit", "FY2024") is None


def test_token_grammar() -> None:
    assert parse_number("(1,072)") == (-1072, 0, None, None)[:1] + parse_number("(1,072)")[1:]  # type: ignore[index]
    value, decimals, suffix, cur = parse_number("€88,035m")  # type: ignore[misc]
    assert (value, decimals, suffix, cur) == (88035, 0, "m", "€")
    assert parse_number("2.30")[1] == 2  # type: ignore[index]
    for bad in ("6.9%", "abc", "(5", "1,2"):
        assert parse_number(bad) is None
    assert period_year("FY24") == 2024 and period_year("2023") == 2023 and period_year("31") is None


def test_every_spec_has_provenance_fields() -> None:
    assert {s.id for s in SPECS} == {
        "basic_eps", "free_cash_flow", "underlying_operating_profit",
        "ice_cream_operating_profit", "parent_investment_in_subsidiaries",
    }  # fmt: skip
    assert (
        json.loads(SupplementalFacts(facts=(), warnings=()).model_dump_json())["schema_version"]
        == "1.0.0"
    )


EXCERPT = Path(__file__).resolve().parents[1] / "golden" / "company_a" / "excerpt.pdf"


def test_the_committed_company_a_excerpt_gives_eps_and_the_parent_investment(
    tmp_path: Path,
) -> None:
    from finintel.parse.text_layer import read_text_layer

    pack = json.loads(
        (
            Path(__file__).resolve().parents[2] / "fixtures" / "expected" / "company_a.json"
        ).read_text()
    )
    r = extract_facts(read_text_layer(EXCERPT), pack)
    eps = r.get("basic_eps", "FY2024")
    parent = r.get("parent_investment_in_subsidiaries", "FY2024")
    assert eps is not None and (eps.value, eps.raw_text, eps.page) == (2.3, "2.30", 141)
    assert parent is not None and (parent.value, parent.unit_scale, parent.page) == (
        88035.0,
        1_000_000,
        197,
    )
    assert parent.sources[0].row_text.startswith("Investments in subsidiaries")


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[2] / "fixtures" / "pdfs" / "company_a.pdf").exists(),
    reason="fixture PDF absent",
)
def test_the_full_report_matches_the_tech_leads_numeric_labels(tmp_path: Path) -> None:
    from finintel.parse.text_layer import read_text_layer

    root = Path(__file__).resolve().parents[2]
    pack = json.loads((root / "fixtures" / "expected" / "company_a.json").read_text())
    qa = {
        q["id"]: q
        for q in json.loads((root / "fixtures" / "expected" / "company_a.qa.json").read_text())[
            "questions"
        ]
    }
    r = extract_facts(read_text_layer(root / "fixtures" / "pdfs" / "company_a.pdf"), pack)
    expected = {
        "basic_eps": qa["n4"]["answer"], "free_cash_flow": qa["n5"]["answer"],
        "underlying_operating_profit": qa["n6"]["answer"],
        "ice_cream_operating_profit": qa["t2"]["answer"],
        "parent_investment_in_subsidiaries": qa["t3"]["answer"],
    }  # fmt: skip
    for fact_id, answer in expected.items():
        f = r.get(fact_id, "FY2024")
        assert f is not None and f.value == answer, (fact_id, f)
    assert not [w for w in r.warnings if w.code == "conflict"]
