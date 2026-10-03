"""E2 ratios (EVAL section 2): compute_ratios on the labelled pack and on the extracted pack,
each against `{company}.ratios.json`, at 1e-9 absolute.

A cell is (period, ratio). An expected null ("value": null, "reason": "missing_input") matches only
a null with that reason; a number matches only a number within tolerance. The locked formula string
must equal the expected one. `matched` counts cells that match from BOTH packs, so a label file and
the pipeline cannot disagree silently. Expected files are read, never written.

Two layouts are read: a list of `{period_id, ratios: {name: {value, formula}}}` (company_a), and
`{ratios: {name: {definition, values: [{period_id, value}]}}}` (company_b), where `definition` is
the formula. An expected period is the pack's period with the same id or, failing that, the same
end date as the labelled period of that id (labels say "2024" where the pipeline says "FY2024").
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from finintel.ratios import compute_ratios

TOLERANCE = 1e-9


def _rows(expected: Sequence[Mapping[str, Any]] | Mapping[str, Any]) -> list[dict[str, Any]]:
    """Both expected layouts as `[{period_id, ratios: {name: {value, formula?}}}]`."""
    if (
        isinstance(expected, Mapping)
        and isinstance(expected.get("ratios"), Mapping)
        and all(isinstance(r, Mapping) and "values" in r for r in expected["ratios"].values())
    ):
        rows: dict[str, dict[str, Any]] = {}
        for name, body in expected["ratios"].items():
            for v in body["values"]:
                row = rows.setdefault(v["period_id"], {"period_id": v["period_id"], "ratios": {}})
                want = {"value": v["value"], "formula": body.get("definition")}
                if "reason" in v:
                    want["reason"] = v["reason"]
                row["ratios"][name] = {
                    k: x for k, x in want.items() if x is not None or k == "value"
                }
        return list(rows.values())
    return [dict(expected)] if isinstance(expected, Mapping) else [dict(r) for r in expected]


def _period_ids(pack: Mapping[str, Any], labelled: Mapping[str, Any]) -> dict[str, str]:
    """Expected (label) period id -> this pack's period id: same id, else same end date."""
    ids = {p["id"] for p in pack.get("periods", [])}
    by_end = {p.get("end_date"): p["id"] for p in pack.get("periods", []) if p.get("end_date")}
    out = {}
    for p in labelled.get("periods", []):
        if p["id"] in ids:
            out[p["id"]] = p["id"]
        elif p.get("end_date") in by_end:
            out[p["id"]] = by_end[p["end_date"]]
    return out


def _cells(
    pack: Mapping[str, Any],
    expected: Sequence[Mapping[str, Any]],
    labelled: Mapping[str, Any] | None = None,
) -> dict[tuple[str, str], str]:
    ratios = compute_ratios(pack)
    by_period = {p.period_id: p for p in ratios.periods}
    ids = _period_ids(pack, labelled or pack)
    out: dict[tuple[str, str], str] = {}
    for period in expected:
        computed = by_period.get(ids.get(period["period_id"], period["period_id"]))
        for name, want in period["ratios"].items():
            got = getattr(computed.ratios, name, None) if computed else None
            out[(period["period_id"], name)] = _verdict(got, want)
    return out


def _verdict(got: Any, want: Mapping[str, Any]) -> str:
    if got is None:
        return "period or ratio missing"
    if got.formula != want.get("formula", got.formula):
        return f"formula {got.formula!r} != {want['formula']!r}"
    if want["value"] is None:
        if got.value is not None:
            return f"expected null, computed {got.value}"
        expected_reason = want.get("reason")
        return (
            "ok"
            if expected_reason in (None, got.reason)
            else f"reason {got.reason!r} != {expected_reason!r}"
        )
    if got.value is None:
        return f"expected {want['value']}, computed null ({got.reason})"
    return (
        "ok"
        if abs(got.value - want["value"]) <= TOLERANCE
        else f"expected {want['value']}, computed {got.value}"
    )


def compare(
    extracted: Mapping[str, Any],
    labelled: Mapping[str, Any],
    expected: Sequence[Mapping[str, Any]] | Mapping[str, Any],
) -> dict[str, Any]:
    rows = _rows(expected)
    from_extracted = _cells(extracted, rows, labelled)
    from_labels = _cells(labelled, rows, labelled)
    cells = [
        {
            "period": p,
            "ratio": r,
            "extracted": from_extracted[(p, r)],
            "labelled": from_labels[(p, r)],
        }
        for (p, r) in from_extracted
    ]
    return {
        "expected": len(cells),
        "matched": sum(1 for c in cells if c["extracted"] == c["labelled"] == "ok"),
        "matched_extracted": sum(1 for c in cells if c["extracted"] == "ok"),
        "matched_labelled": sum(1 for c in cells if c["labelled"] == "ok"),
        "tolerance": TOLERANCE,
        "cells": cells,
    }
