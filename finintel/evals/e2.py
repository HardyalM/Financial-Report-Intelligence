"""E2 ratios (EVAL section 2): compute_ratios on the labelled pack and on the extracted pack,
each against `{company}.ratios.json`, at 1e-9 absolute.

A cell is (period, ratio). An expected null ("value": null, "reason": "missing_input") matches only
a null with that reason; a number matches only a number within tolerance. The locked formula string
must equal the expected one. `matched` counts cells that match from BOTH packs, so a label file and
the pipeline cannot disagree silently. Expected files are read, never written.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from finintel.ratios import compute_ratios

TOLERANCE = 1e-9


def _cells(
    pack: Mapping[str, Any], expected: Sequence[Mapping[str, Any]]
) -> dict[tuple[str, str], str]:
    ratios = compute_ratios(pack)
    by_period = {p.period_id: p for p in ratios.periods}
    out: dict[tuple[str, str], str] = {}
    for period in expected:
        computed = by_period.get(period["period_id"])
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
    rows = [expected] if isinstance(expected, Mapping) else list(expected)
    from_extracted, from_labels = _cells(extracted, rows), _cells(labelled, rows)
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
