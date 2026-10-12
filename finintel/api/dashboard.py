"""The dashboard's view of a report: counts and headlines read from the stored packs.

Pure functions of what the pipeline stored (StatementPack, RatioPack, commentary). Nothing is
computed here but counts: every value shown is the ratio engine's, as it stored it.
"""

from __future__ import annotations

from typing import Any

# Ratios a reader looks for first, in that order (corporate first; a bank's own two lead for a bank).
CORPORATE = ("operating_margin", "roce", "current_ratio", "debt_to_equity")
BANK = ("cost_to_income", "loan_to_deposit")


def figure_counts(pack: dict[str, Any] | None) -> dict[str, int] | None:
    """The current period's items by how each was settled: read, derived, manual, empty."""
    if not pack or not pack.get("periods"):
        return None
    current = pack["periods"][0]["id"]
    counts = {"read": 0, "derived": 0, "manual": 0, "empty": 0}
    for item in pack.get("items", {}).values():
        value = next((v for v in item.get("values", []) if v.get("period_id") == current), None)
        if value is None:
            continue
        engine = str(value.get("engine") or "")
        if value.get("value") is None:
            counts["empty"] += 1
        elif engine.startswith("human_override"):
            counts["manual"] += 1
        elif engine == "derived":
            counts["derived"] += 1
        else:
            counts["read"] += 1
    return counts


def ratio_headlines(ratios: dict[str, Any] | None, document_type: str) -> list[dict[str, Any]]:
    """The headline ratios for the current period, with the engine's change against the prior."""
    if not ratios or not ratios.get("periods"):
        return []
    period = ratios["periods"][0]
    by_name: dict[str, Any] = period.get("ratios", {})
    change = next(
        (c for c in ratios.get("changes", []) if c.get("to_period_id") == period.get("period_id")),
        None,
    )
    order = (*BANK, *CORPORATE) if document_type == "bank" else (*CORPORATE, *BANK)
    out = []
    for name in order:
        r = by_name.get(name)
        if not r or r.get("status") == "not_applicable":
            continue
        moved = (change or {}).get("ratios", {}).get(name) or {}
        out.append({
            "name": name, "label": r.get("label") or name.replace("_", " ").capitalize(),
            "value": r.get("value"), "unit": r.get("unit", "fraction"), "status": r.get("status", ""),
            "flags": list(r.get("flags", [])), "change_kind": moved.get("kind"),
            "change": moved.get("value"),
        })  # fmt: skip
    return out


def commentary_headline(output: dict[str, Any] | None, stale: bool) -> dict[str, Any] | None:
    if not output:
        return None
    topics = output.get("topics", [])
    paragraphs = [p for t in topics for p in t.get("paragraphs", [])]
    bullets = output.get("executive_summary", {}).get("bullets", [])
    citations = sum(len(p.get("citations", [])) for p in [*paragraphs, *bullets])
    return {
        "mode": output.get("mode", ""), "topics_ok": sum(t.get("status") == "ok" for t in topics),
        "topics": len(topics), "citations": citations, "stale": stale,
    }  # fmt: skip


def waiting_for(status: str, open_review: int) -> str | None:
    """What the report waits for from a person, if anything."""
    if status == "needs_unit_confirmation":
        return "unit"
    if status == "needs_document_type":
        return "document_type"
    if status == "failed":
        return "failed"
    return "review" if open_review else None


def document_type_of(row_type: str, pack: dict[str, Any] | None) -> str:
    """The document's type: as set on the document, else as the locator profiled it."""
    if row_type != "other" or not pack:
        return row_type
    return str(pack.get("document_type") or row_type)
