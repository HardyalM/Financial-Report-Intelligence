"""The dashboard view's pure functions (no database): counts and headlines from stored packs."""

from __future__ import annotations

from finintel.api import dashboard as dash


def test_figures_are_counted_by_how_they_were_settled_for_the_current_period() -> None:
    pack = {
        "periods": [{"id": "FY2025"}, {"id": "FY2024"}],
        "items": {
            "revenue": {"values": [{"period_id": "FY2025", "value": 10.0, "engine": "pdfplumber"},
                                   {"period_id": "FY2024", "value": None, "engine": None}]},
            "total_debt": {"values": [{"period_id": "FY2025", "value": 4.0, "engine": "derived"}]},
            "net_income": {"values": [{"period_id": "FY2025", "value": 2.0, "engine": "human_override"}]},
            "total_assets": {"values": [{"period_id": "FY2025", "value": None, "engine": None}]},
        },
    }  # fmt: skip
    assert dash.figure_counts(pack) == {"read": 1, "derived": 1, "manual": 1, "empty": 1}
    assert dash.figure_counts(None) is None


def test_ratio_headlines_are_the_engines_values_bank_ratios_first_for_a_bank() -> None:
    ratios = {
        "periods": [{"period_id": "FY2025", "ratios": {
            "operating_margin": {"value": None, "unit": "fraction", "status": "not_applicable", "flags": []},
            "cost_to_income": {"value": 0.62, "unit": "fraction", "status": "ok", "flags": [], "label": "Cost-to-income"},
            "loan_to_deposit": {"value": 0.91, "unit": "fraction", "status": "ok", "flags": []},
        }}],
        "changes": [{"to_period_id": "FY2025", "ratios": {"cost_to_income": {"kind": "percentage_points", "value": -0.012}}}],
    }  # fmt: skip
    out = dash.ratio_headlines(ratios, "bank")
    assert [r["name"] for r in out] == ["cost_to_income", "loan_to_deposit"]  # n/a dropped
    assert out[0]["value"] == 0.62 and out[0]["change"] == -0.012
    assert out[0]["change_kind"] == "percentage_points"


def test_what_a_report_waits_for() -> None:
    assert dash.waiting_for("needs_unit_confirmation", 0) == "unit"
    assert dash.waiting_for("needs_document_type", 3) == "document_type"
    assert dash.waiting_for("ready", 2) == "review"
    assert dash.waiting_for("ready", 0) is None
    assert dash.document_type_of("other", {"document_type": "corporate"}) == "corporate"
    assert dash.document_type_of("bank", {"document_type": "corporate"}) == "bank"
