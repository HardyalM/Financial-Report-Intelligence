"""Held for sale (tech lead, 2026-10-11): excluded from current assets and current liabilities,
included in total assets.

The layout is company_c's (Tesco, p.139): the current-assets section closes with a subtotal, then a
held-for-sale line, then a second unlabelled subtotal. The subtotal before the held-for-sale line is
current assets. Nothing is subtracted when a company folds held for sale into its only subtotal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.extract.helpers import bs_rows, run_spec, spec_data, values, warnings


def _items(result: Any) -> dict[str, Any]:
    assert result.pack is not None
    items: dict[str, Any] = result.pack["items"]
    return items


def _tesco_layout(*, held_label: str = "Assets classified as held for sale") -> dict[str, Any]:
    data = spec_data("company_before_group")
    rows = bs_rows(data, 4)
    at = next(i for i, r in enumerate(rows) if r.get("id") == "current_assets") + 1
    rows[at:at] = [
        {"label": held_label, "id": "held", "note": "8", "values": ["50", "80"]},
        {
            "label": "",
            "id": "current_with_held",
            "values": ["2,750", "2,580"],
            "style": "subtotal",
            "sum_of": ["current_assets", "held"],
        },
    ]
    total = next(r for r in rows if r["label"] == "Total assets")
    total["values"] = ["10,750", "10,350"]
    total["sum_of"] = ["non_current_assets", "current_with_held"]
    net = next(r for r in rows if r["label"] == "Net assets")
    net["values"], equity = ["4,300", "3,980"], ["4,300", "3,980"]
    next(r for r in rows if r["label"] == "Total equity")["values"] = equity
    next(r for r in rows if r["label"] == "Retained earnings")["values"] = ["4,050", "3,730"]
    return data


def test_current_assets_is_the_subtotal_before_held_for_sale(tmp_path: Path) -> None:
    result = run_spec(_tesco_layout(), tmp_path)
    assert values(result, "current_assets") == {"FY2025": 2700.0, "FY2024": 2500.0}
    assert values(result, "total_assets") == {"FY2025": 10750.0, "FY2024": 10350.0}  # printed
    assert not warnings(result, "alias_weak", "current_assets")
    assert not warnings(result, "arithmetic_check_failed", "current_assets")  # 8,000 + 2,700 + 50


def test_derived_total_assets_includes_held_for_sale(tmp_path: Path) -> None:
    data = _tesco_layout()
    rows = bs_rows(data, 4)
    rows[:] = [r for r in rows if r["label"] not in ("Total assets", "Net assets")]
    result = run_spec(data, tmp_path)
    assert values(result, "total_assets") == {"FY2025": 10750.0, "FY2024": 10350.0}
    [ta] = [v for v in _items(result)["total_assets"]["values"] if v["period_id"] == "FY2025"]
    assert [d["item"] for d in ta["derived_from"]] == [
        "non_current_assets", "current_assets", "assets_held_for_sale"
    ]  # fmt: skip
    assert _items(result)["assets_held_for_sale"]["values"][0]["value"] == 50.0


def test_two_subtotals_without_a_held_for_sale_line_are_not_resolved_by_it(tmp_path: Path) -> None:
    result = run_spec(_tesco_layout(held_label="Other current assets"), tmp_path)
    assert values(result, "current_assets") == {"FY2025": None, "FY2024": None}
    assert "assets_held_for_sale" not in _items(result)


def test_held_for_sale_folded_into_the_only_subtotal_is_not_subtracted(tmp_path: Path) -> None:
    data = spec_data("company_before_group")
    rows = bs_rows(data, 4)
    ca = next(r for r in rows if r.get("id") == "current_assets")
    at = rows.index(ca)
    rows.insert(at, {"label": "Assets held for sale", "id": "held", "values": ["50", "80"]})
    ca["values"], ca["sum_of"] = ["2,750", "2,580"], [*ca["sum_of"], "held"]
    total = next(r for r in rows if r["label"] == "Total assets")
    total["values"] = ["10,750", "10,350"]
    for label in ("Net assets", "Total equity"):
        next(r for r in rows if r["label"] == label)["values"] = ["4,300", "3,980"]
    next(r for r in rows if r["label"] == "Retained earnings")["values"] = ["4,050", "3,730"]
    result = run_spec(data, tmp_path)
    assert values(result, "current_assets") == {"FY2025": 2750.0, "FY2024": 2580.0}
    assert "assets_held_for_sale" not in _items(result)  # not derived from: not emitted
