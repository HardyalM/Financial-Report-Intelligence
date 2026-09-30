"""RatioEngine: the locked v1 ratios, computed from a StatementPack and nothing else.

Locked definitions (CLAUDE.md; a drift test compares these strings with that file):

    operating_margin = operating_profit / revenue
    current_ratio    = current_assets / current_liabilities
    debt_to_equity   = total_debt / total_equity
    roce             = operating_profit / (total_assets - current_liabilities)

ROCE uses year-end balances, not averages, in v1.

`total_equity` includes non-controlling interests; `total_debt` is interest-bearing borrowings plus
lease liabilities where separately presented (resolved, with provenance, in the StatementPack).
Nothing here reads prose, infers a missing input, or rounds: values are exact Decimal quotients
converted once to float. A computed value is never hidden (ADR-008); flags sit beside it.

Null, applicability and reason (ADR-008): a null input gives `value: null` and `reason:
"missing_input"`, exactly as CLAUDE.md says. A zero denominator gives `division_by_zero`.
Applicability (from the document profile) is separate: a bank's ratios are `not_applicable`, an
ambiguous document's are `withheld`. A v1.0.0 pack carries no document profile; it is treated as
corporate and its own null inputs decide, because nothing else is known.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from itertools import pairwise
from typing import Any

from finintel.contracts.ratio_pack import RatioPack

RATIO_SCHEMA_VERSION = "1.0.0"

# Locked formulas, verbatim from CLAUDE.md.
FORMULAS: dict[str, str] = {
    "operating_margin": "operating_profit / revenue",
    "current_ratio": "current_assets / current_liabilities",
    "debt_to_equity": "total_debt / total_equity",
    "roce": "operating_profit / (total_assets - current_liabilities)",
}
FORMULA_TEXT: dict[str, str] = {
    "operating_margin": "Operating profit ÷ Revenue",
    "current_ratio": "Current assets ÷ Current liabilities",
    "debt_to_equity": "Total debt ÷ Total equity",
    "roce": "Operating profit ÷ (Total assets - Current liabilities)",
}
LABELS = {
    "operating_margin": "Operating margin",
    "current_ratio": "Current ratio",
    "debt_to_equity": "Debt-to-equity",
    "roce": "ROCE",
}
INPUTS: dict[str, tuple[str, ...]] = {
    "operating_margin": ("operating_profit", "revenue"),
    "current_ratio": ("current_assets", "current_liabilities"),
    "debt_to_equity": ("total_debt", "total_equity"),
    "roce": ("operating_profit", "total_assets", "current_liabilities"),
}
UNIT = {
    "operating_margin": "fraction",
    "roce": "fraction",
    "current_ratio": "multiple",
    "debt_to_equity": "multiple",
}
#: Margin-type ratios change in percentage points; multiples as an absolute difference.
POINT_RATIOS = frozenset({"operating_margin", "roce"})
CHANGE_ITEMS = (
    "revenue", "operating_profit", "profit_before_tax", "net_income", "current_assets",
    "current_liabilities", "total_assets", "total_equity", "total_debt",
)  # fmt: skip
_BADGE_BY_ENGINE = {
    "derived": "derived",
    "human_override": "manual",
    "human_override_unanchored": "manual_unanchored",
}


@dataclass(frozen=True)
class _Input:
    item: str
    value: Decimal | None
    page: int | None
    badges: tuple[str, ...]


def pack_sha256(pack: Mapping[str, Any]) -> str:
    """SHA-256 of the canonical JSON of a StatementPack (keys sorted, no whitespace)."""
    canonical = json.dumps(pack, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_ratios(pack: Mapping[str, Any]) -> RatioPack:
    """The locked ratios for every period in the pack, plus period-on-period changes."""
    items: Mapping[str, Any] = pack["items"]
    periods = sorted(
        pack["periods"], key=lambda p: (p.get("end_date") or "", p["id"]), reverse=True
    )
    profile = (pack.get("document_type"), pack.get("balance_sheet_classified"))
    built: list[dict[str, Any]] = []
    values: dict[str, dict[str, Decimal | None]] = {}
    for period in periods:
        pid = period["id"]
        inputs = {
            name: _input(items, name, pid) for name in {n for ns in INPUTS.values() for n in ns}
        }
        values[pid] = {n: i.value for n, i in inputs.items()}
        ratios = {name: _ratio(name, inputs, pid, profile) for name in FORMULAS}
        built.append({"period_id": pid, "end_date": period.get("end_date"), "ratios": ratios})
    out = {
        "schema_version": RATIO_SCHEMA_VERSION,
        "statement_pack_sha": pack_sha256(pack),
        "formulas_locked": True,
        "currency": pack.get("currency"),
        "unit_scale": pack.get("unit_scale"),
        "document_type": pack.get("document_type"),
        "periods": built,
        "changes": _changes(built, items, periods),
        "warnings": _warnings(built),
    }
    return RatioPack.model_validate(out)


def _input(items: Mapping[str, Any], name: str, period_id: str) -> _Input:
    value = next(
        (v for v in (items.get(name) or {}).get("values", []) if v["period_id"] == period_id), None
    )
    if value is None or value.get("value") is None:
        return _Input(name, None, (value or {}).get("page"), ())
    badge = _BADGE_BY_ENGINE.get(value.get("engine") or "")
    return _Input(name, Decimal(str(value["value"])), value.get("page"), (badge,) if badge else ())


def _applicability(name: str, profile: tuple[Any, Any]) -> tuple[str, str | None]:
    """(applicability, explanation) from the document profile (EXTRACTION section 1.4 matrix)."""
    kind, classified = profile
    if kind == "bank":
        return (
            "not_applicable",
            "Not applicable to banks: the statements have no revenue line or current/non-current "
            "split, and deposits are not corporate debt",
        )
    if name == "current_ratio" and classified is False:
        return (
            "not_applicable",
            "Not applicable: the balance sheet has no current/non-current split",
        )
    if kind == "other":
        return "withheld", "Document type unclear: confirm the type to show this ratio"
    if kind == "nhs_trust" and name != "current_ratio":
        return "withheld", "NHS trust treatment of this ratio is undecided (OQ-5)"
    return "applicable", None


def _ratio(
    name: str, inputs: Mapping[str, _Input], period_id: str, profile: tuple[Any, Any]
) -> dict[str, Any]:
    used = {n: inputs[n] for n in INPUTS[name]}
    applicability, explanation = _applicability(name, profile)
    missing = [n for n, i in used.items() if i.value is None]
    value: Decimal | None = None
    reason: str | None = None
    flags: list[str] = []
    if missing:
        reason = "missing_input"
    else:
        numerator, denominator = _terms(
            name, {n: i.value for n, i in used.items() if i.value is not None}
        )
        if denominator == 0:
            reason = "division_by_zero"
        else:
            value = numerator / denominator
            if denominator < 0:
                flags.append("negative_denominator")
    shown = float(value) if value is not None else None
    if applicability != "applicable" and not missing:
        shown, reason = None, None  # not shown; the explanation says why
    status = (
        "ok" if shown is not None else (applicability if applicability != "applicable" else "null")
    )
    return {
        "name": name,
        "label": LABELS[name],
        "value": shown,
        "status": status,
        "reason": reason,
        "applicability": applicability,
        "explanation": explanation,
        "missing_inputs": missing,
        "flags": flags if shown is not None else [],
        "formula": FORMULAS[name],
        "formula_text": FORMULA_TEXT[name],
        "unit": UNIT[name],
        "inputs": {
            n: {
                "item": n,
                "value": float(i.value) if i.value is not None else None,
                "period_id": period_id,
                "page": i.page,
                "badges": list(i.badges),
            }
            for n, i in used.items()
        },
    }


def _terms(name: str, v: Mapping[str, Decimal]) -> tuple[Decimal, Decimal]:
    if name == "operating_margin":
        return v["operating_profit"], v["revenue"]
    if name == "current_ratio":
        return v["current_assets"], v["current_liabilities"]
    if name == "debt_to_equity":
        return v["total_debt"], v["total_equity"]
    return v["operating_profit"], v["total_assets"] - v["current_liabilities"]  # roce


def _changes(
    built: list[dict[str, Any]], items: Mapping[str, Any], periods: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    changes = []
    for later, earlier in pairwise(built):
        ratios: dict[str, dict[str, Any]] = {}
        for name in FORMULAS:
            a, b = later["ratios"][name]["value"], earlier["ratios"][name]["value"]
            diff = (
                None
                if a is None or b is None
                else float(
                    (Decimal(str(a)) - Decimal(str(b))) * (100 if name in POINT_RATIOS else 1)
                )
            )
            ratios[name] = {
                "kind": "percentage_points" if name in POINT_RATIOS else "absolute",
                "value": diff,
            }
        rows: dict[str, dict[str, float | None]] = {}
        for item in CHANGE_ITEMS:
            a, b = (
                _input(items, item, later["period_id"]).value,
                _input(items, item, earlier["period_id"]).value,
            )
            if a is None or b is None:
                rows[item] = {"absolute": None, "percent": None}
            else:
                rows[item] = {
                    "absolute": float(a - b),
                    "percent": float((a - b) / abs(b) * 100) if b != 0 else None,
                }
        changes.append(
            {
                "from_period_id": earlier["period_id"],
                "to_period_id": later["period_id"],
                "ratios": ratios,
                "items": rows,
            }
        )
    return changes


def _warnings(built: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for period in built:
        for name, ratio in period["ratios"].items():
            if "negative_denominator" in ratio["flags"]:
                out.append(
                    {
                        "code": "negative_denominator",
                        "message": f"{ratio['label']} for {period['period_id']} has a negative "
                        "denominator; the value is shown and is not meaningful",
                        "ratio": name,
                        "period_id": period["period_id"],
                    }
                )
    return out
