"""M8.2 (OQ-4 = B): reported metrics, the bank's own CET1 ratio and net interest margin.

Shown "as reported", found by deterministic patterns, never computed and never an input to a
ratio. Every value_text is a verbatim substring of its quote, and every quote of its chunk.
"""

from __future__ import annotations

import ast

import pytest

from finintel.commentary.reported import Found, find_reported_metrics
from finintel.narrative.models import Chunk
from finintel.ratios import compute_ratios
from tests.commentary.builders import ROOT, chunk

PERIODS = [{"id": "FY2024", "end_date": "2024-12-31"}, {"id": "FY2023", "end_date": "2023-12-31"}]


def _find(*texts: str) -> tuple[Found, dict[str, Chunk]]:
    chunks = [chunk(f"c{i}", t, page=10 + i, char_start=1000 * i) for i, t in enumerate(texts)]
    return find_reported_metrics(chunks, PERIODS), {c.chunk_id: c for c in chunks}


def test_value_text_is_a_substring_of_its_verified_quote() -> None:
    found, chunks = _find(
        "Capital remained strong. The Group's CET1 capital ratio at 31 December 2024 was 14.2 per "
        "cent (31 December 2023: 14.6 per cent). Other text follows.",
        "Income rose, with a banking net interest margin of 2.95 per cent (2023: 3.11 per cent), "
        "in line with guidance.",
    )
    metrics = found.metrics
    assert {(m.id, m.period_id, m.value) for m in metrics} == {
        ("cet1_ratio", "FY2024", 14.2), ("cet1_ratio", "FY2023", 14.6),
        ("net_interest_margin", "FY2024", 2.95), ("net_interest_margin", "FY2023", 3.11),
    }  # fmt: skip
    for m in metrics:
        assert m.value_text in m.quote  # the gate's test
        text = chunks[m.chunk_id].text
        assert text[m.char_start : m.char_end] == m.quote  # the quote is verbatim from the chunk
        assert float(m.value_text.split()[0].rstrip("%")) == m.value  # parsed from value_text


def test_targets_requirements_and_quarters_are_never_the_reported_figure() -> None:
    found, _ = _find(
        "We expect banking net interest margin of 3.05 per cent in 2025.",
        "The minimum Pillar 1 CET1 capital requirement of 4.5 per cent applies.",
        "The notes convert should the CET1 ratio of the Group fall below 7.0 per cent.",
        "This resulted in an increase in banking net interest margin to 2.97 per cent in the "
        "fourth quarter.",
    )
    assert found.metrics == []


def test_pro_forma_is_its_own_metric() -> None:
    found, _ = _find(
        "The Group's pro forma CET1 capital ratio at 31 December 2024 was 13.5 per cent "
        "(31 December 2023: 13.7 per cent pro forma), in line with guidance."
    )
    got = {(m.id, m.period_id, m.value, m.basis) for m in found.metrics}
    assert got == {
        ("cet1_ratio_pro_forma", "FY2024", 13.5, "pro forma"),
        ("cet1_ratio_pro_forma", "FY2023", 13.7, "pro forma"),
    }


def test_a_figure_without_a_period_only_corroborates() -> None:
    alone, _ = _find("The year closed with a banking net interest margin of 2.95 per cent.")
    assert alone.metrics == []  # no year: not shown on its own
    agree, _ = _find(
        "The year closed with a banking net interest margin of 2.95 per cent.",
        "Margin: the banking net interest margin was 2.95 per cent (2023: 3.11 per cent).",
    )
    [m24] = [m for m in agree.metrics if m.period_id == "FY2024"]
    assert m24.page == 11  # cited where the period is stated, not where it is merely repeated


def test_disagreeing_figures_are_not_shown_and_the_reason_is_kept() -> None:
    found, _ = _find(
        "The Group's CET1 ratio at 31 December 2024 was 14.2 per cent.",
        "The Group's CET1 capital ratio at 31 December 2024 was 14.0 per cent.",
    )
    assert not [m for m in found.metrics if m.period_id == "FY2024"]
    [note] = found.notes
    assert "14.0" in note and "14.2" in note and "not shown" in note


def test_no_ratio_pack_input_references_a_reported_metric() -> None:
    """The gate's second test: reported metrics never feed a ratio, by data and by import."""
    from tests.commentary.builders import company_pack

    ratios = compute_ratios(company_pack())
    reported = {"cet1_ratio", "cet1_ratio_pro_forma", "net_interest_margin"}
    for period in ratios.periods:
        for name in ("operating_margin", "current_ratio", "debt_to_equity", "roce"):
            assert not reported & set(getattr(period.ratios, name).inputs)
    for path in (ROOT / "finintel" / "ratios").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules = {
            n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module
        } | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert not any("reported" in m or m.startswith("finintel.commentary") for m in modules), (
            path
        )


COMPANY_B = ROOT / "fixtures" / "pdfs" / "company_b.pdf"


@pytest.mark.skipif(not COMPANY_B.exists(), reason="company_b.pdf is not committed")
def test_lloyds_states_its_cet1_ratio_and_net_interest_margin() -> None:
    from finintel.cli.chunks_cmd import chunk_pdf

    _, _, chunks, _ = chunk_pdf(str(COMPANY_B), ROOT / "artifacts" / "cache")
    found = find_reported_metrics(chunks, PERIODS)
    got = {(m.id, m.period_id): (m.value, m.page) for m in found.metrics}
    assert got == {
        ("cet1_ratio", "FY2024"): (14.2, 72), ("cet1_ratio", "FY2023"): (14.6, 72),
        ("cet1_ratio_pro_forma", "FY2024"): (13.5, 72),
        ("cet1_ratio_pro_forma", "FY2023"): (13.7, 72),
        ("net_interest_margin", "FY2024"): (2.95, 69),
        ("net_interest_margin", "FY2023"): (3.11, 69),
    }  # fmt: skip
    assert found.notes == []
    assert all(m.value_text in m.quote for m in found.metrics)


def test_the_finder_never_asks_a_model() -> None:
    tree = ast.parse((ROOT / "finintel" / "commentary" / "reported.py").read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not any(m.startswith("finintel.llm") for m in imported)
