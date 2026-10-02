"""The read-only slice of an extraction report the report screen needs (UI.md sections 4 and 6.2).

Row states and provenance come from here: which engine families agreed for each value, the
arithmetic checks, where each statement was found, and, for an item that stayed null, the labels
that were searched for. It is a view of what extraction recorded; nothing is recomputed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from finintel.mapping.aliases import load_aliases

STATEMENT_NAMES = {
    "income_statement": "consolidated income statement",
    "balance_sheet": "consolidated balance sheet",
    "comprehensive_income": "statement of comprehensive income",
    "cash_flow": "cash flow statement",
    "changes_in_equity": "statement of changes in equity",
}


#: Items built from printed lines (docs/SCHEMA.md section 5): the search is for their components.
COMPONENTS = {
    "total_debt": (
        "borrowings_current", "borrowings_non_current",
        "lease_liabilities_current", "lease_liabilities_non_current",
    ),
}  # fmt: skip


def searched_for(
    pack: Mapping[str, Any], statements: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    """For every item with no value in any period: the statement and pages searched, the labels
    tried (a derived item's are its components'), and the extraction warnings about it."""
    doc_type = str(pack.get("document_type") or "corporate")
    corporate = load_aliases("corporate")
    #: Labels are listed only where they were tried: there is no alias map for other types yet.
    specs = corporate if doc_type in ("corporate", "other") else {}
    out: dict[str, dict[str, Any]] = {}
    for item_id, item in pack.get("items", {}).items():
        if any(v.get("value") is not None for v in item.get("values", [])):
            continue
        names = COMPONENTS.get(item_id, (item_id,))
        labels: list[str] = []
        for name in names:
            component = specs.get(name)
            for label in sorted(component.include_exact) if component else []:
                if label not in labels:
                    labels.append(label)
        home = corporate.get(names[0])
        statement = home.statement.value if home else str(item.get("statement") or "")
        located = statements.get(statement) or {}
        out[item_id] = {
            "statement": statement,
            "pages": list(located.get("pages", [])),
            "labels": labels[:8],
            "components": list(names) if item_id in COMPONENTS else [],
            "warnings": [w for w in pack.get("warnings", []) if w.get("item") == item_id],
        }
    return out


def extraction_view(
    report: Mapping[str, Any] | None, pack: Mapping[str, Any] | None
) -> dict[str, Any] | None:
    if not report or pack is None:
        return None
    locator = report.get("locator") or {}
    candidates = report.get("candidates") or {}
    families = sorted({f for c in candidates.values() for f in c.get("families", [])})
    return {
        "statements": locator.get("statements", {}),
        "statement_names": STATEMENT_NAMES,
        "candidates": candidates,
        "checks": report.get("checks", []),
        "engines": report.get("engines", []),
        "engine_skipped": report.get("engine_skipped", {}),
        "families": families,
        "searched_for": searched_for(pack, locator.get("statements", {})),
    }
