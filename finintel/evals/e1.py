"""E1 golden cells (EVAL section 2): extracted StatementPack against fixtures/expected/{stem}.json.

Per labelled (item, period) cell:
- label null: matched if extracted null; any published value is silent_wrong
- label value, extracted equal in value, period, page and canonical raw_text: matched
  (a derived value matches on value and derived_from only: it has no page or raw text)
- extracted null with a warning for that item: honest_null (an acceptable failure)
- extracted null without a warning, or any published wrong value: silent_wrong
A pack unit scale or currency that differs from the label fails every cell (unit_errors).
Expected files are read, never written.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from finintel.tables.numbers import canonical

FLAG_CODES = {
    "missing_item", "low_confidence", "parser_disagreement", "alias_weak",
    "arithmetic_check_failed", "period_ambiguous", "entity_scope_ambiguous",
}  # fmt: skip


def compare(
    pack: dict[str, Any], expected: dict[str, Any], report: dict[str, Any] | None = None
) -> dict[str, Any]:
    labelled = [(i, v) for i, it in expected["items"].items() for v in it["values"]]
    unit_error = (pack["currency"], pack["unit_scale"]) != (
        expected["currency"],
        expected["unit_scale"],
    )
    flagged = {w["item"] for w in pack["warnings"] if w["code"] in FLAG_CODES and w.get("item")}
    cells, counts = [], {"matched": 0, "honest_null": 0, "silent_wrong": 0}
    for item, want in labelled:
        got = next(
            (
                v
                for v in pack["items"].get(item, {}).get("values", [])
                if v["period_id"] == want["period_id"]
            ),
            None,
        )
        status = _status(item, want, got, flagged, unit_error)
        counts[status] += 1
        cells.append(
            {
                "item": item,
                "period": want["period_id"],
                "status": status,
                "expected": want["value"],
                "got": got["value"] if got else None,
                "page": (got or {}).get("page"),
            }
        )
    candidates = (report or {}).get("candidates", {})
    return {
        "labelled": len(labelled),
        **counts,
        "unit_errors": len(labelled) if unit_error else 0,
        "cells": cells,
        "published_llm_pointer": sum(
            1
            for c in candidates.values()
            if c.get("decision", "").startswith("published") and c.get("method") == "llm_pointer"
        ),
        "published_vision_only": 0,
    }


def _status(
    item: str,
    want: dict[str, Any],
    got: dict[str, Any] | None,
    flagged: set[str | None],
    unit_error: bool,
) -> str:
    value = got["value"] if got else None
    if unit_error:
        return "silent_wrong" if value is not None else "honest_null"
    if want["value"] is None:
        return "matched" if value is None else "silent_wrong"
    if value is None:
        return "honest_null" if item in flagged else "silent_wrong"
    if got is None or value != want["value"]:
        return "silent_wrong"
    if got.get("engine") == "derived":
        return "matched"
    same = got.get("page") == want["page"] and canonical(got.get("raw_text")) == canonical(
        want.get("raw_text")
    )
    return "matched" if same else "silent_wrong"


def report_json(
    e1: dict[str, Any], company: str, engines: str, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    body = {
        k: v for k, v in e1.items() if k not in ("published_llm_pointer", "published_vision_only")
    }
    return {
        "company": company,
        "engines": engines,
        "e1": body,
        "e6": {
            "published_llm_pointer": e1["published_llm_pointer"],
            "published_vision_only": e1["published_vision_only"],
        },
        **(extra or {}),
    }


def write_report(report: dict[str, Any], out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return out
