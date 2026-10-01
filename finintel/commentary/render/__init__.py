"""Placeholder rendering and GROUND_TRUTH_NUMBERS (RAG sections 4.1-4.2, ADR-003, ADR-005).

Numbers in commentary are written by code. The model supplies a template with placeholders:

    {{item:<id>:<period>}}  {{ratio:<id>:<period>}}  {{change:item|ratio:<id>:<from>:<to>}}

and this module turns each into text from the StatementPack and RatioPack alone. Rounding is
half-up on exact decimals, never float formatting. Nothing here estimates: a null stays null and
renders as "not available (<reason>)". Each entry carries the *direction* of the change into its
period (up, down or flat, judged on the rounded value a reader sees), which validator V7 compares
with the direction words the model wrote.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from finintel.contracts.ratio_pack import RatioPack
from finintel.facts.models import SupplementalFact, SupplementalFacts

PLACEHOLDER = re.compile(r"\{\{([^{}]*)\}\}")
SYMBOLS = {"GBP": "£", "EUR": "€", "USD": "$"}
REASON_TEXT = {
    "missing_input": "missing input",
    "division_by_zero": "division by zero",
    "not_applicable": "not applicable",
    "withheld": "withheld",
    "unit_unknown": "unit not confirmed",
    "conflicting_sources": "sources disagree",
}
Direction = str  # "up" | "down" | "flat"


@dataclass(frozen=True)
class TruthEntry:
    key: str
    rendered: str | None  # None when the value is not available
    status: str  # "ok" | "null"
    reason: str | None
    direction: Direction | None  # None when no comparison is provided
    value: float | None = None  # the pack value behind `rendered`, in pack units (scoring only)
    amount: float | None = None  # value in base currency units (item and fact values; scoring only)
    pages: tuple[int, ...] = ()  # printed source pages; never shown to the model
    note: str | None = None  # e.g. "non-GAAP measure"

    def text(self) -> str:
        if self.rendered is not None:
            return self.rendered
        return f"not available ({REASON_TEXT.get(self.reason or '', self.reason or 'unavailable')})"


def _dec(value: float) -> Decimal:
    return Decimal(str(value))


def _round(value: Decimal, places: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def render_money(value: float, unit_scale: int, currency: str | None) -> str:
    """£907.5m, £13.9bn, £12.3k or £950: the figure times its unit scale, one decimal."""
    symbol = SYMBOLS.get(currency or "", f"{currency} " if currency else "")
    amount = _dec(value) * unit_scale
    sign = "-" if amount < 0 else ""
    magnitude = abs(amount)
    ladder = ((Decimal(10) ** 9, "bn"), (Decimal(10) ** 6, "m"), (Decimal(10) ** 3, "k"))
    for index, (floor, suffix) in enumerate(ladder):
        if magnitude >= floor:
            scaled = _round(magnitude / floor, 1)
            if scaled >= 1000 and index > 0:  # 999.96m rounds to 1000.0m: say 1.0bn instead
                floor, suffix = ladder[index - 1]
                scaled = _round(magnitude / floor, 1)
            return f"{sign}{symbol}{scaled}{suffix}"
    return f"{sign}{symbol}{_round(magnitude, 0):,}"


def render_ratio(value: float, unit: str) -> str:
    """Fractions as a percentage to one decimal (15.5%); multiples to two decimals (1.54x)."""
    if unit == "fraction":
        return f"{_round(_dec(value) * 100, 1)}%"
    return f"{_round(_dec(value), 2)}x"


def _signed(value: float, places: int) -> str:
    """Always signed; a value that rounds to zero prints as unsigned zero, never "-0.0"."""
    rounded = _round(_dec(value), places)
    return f"{abs(rounded)}" if rounded == 0 else f"{rounded:+}"


def render_point_change(value: float) -> str:
    return f"{_signed(value, 1)} pp"


def render_multiple_change(value: float) -> str:
    return f"{_signed(value, 2)}x"


def render_percent_change(value: float) -> str:
    return f"{_signed(value, 1)}%"


def _direction(rounded: Decimal) -> Direction:
    return "up" if rounded > 0 else "down" if rounded < 0 else "flat"


def build_ground_truth(
    pack: Mapping[str, Any], ratios: RatioPack, facts: SupplementalFacts | None = None
) -> dict[str, TruthEntry]:
    """Every placeholder the model may use, keyed `kind:id:period[:to]`, built by code."""
    truth: dict[str, TruthEntry] = {}
    unit_scale = pack.get("unit_scale")
    currency = pack.get("currency")
    into: dict[str, Any] = {c.to_period_id: c for c in ratios.changes}  # change into each period

    def put(entry: TruthEntry) -> None:
        truth[entry.key] = entry

    for item_id, item in pack["items"].items():
        for pv in item.get("values", []):
            key = f"item:{item_id}:{pv['period_id']}"
            change = into.get(pv["period_id"])
            direction: Direction | None = None
            if change is not None and item_id in change.items:
                absolute = change.items[item_id].absolute
                direction = None if absolute is None else _direction(_dec(absolute))
            if pv.get("value") is None:
                put(TruthEntry(key, None, "null", "missing_input", None))
            elif unit_scale is None:
                put(TruthEntry(key, None, "null", "unit_unknown", None))
            else:
                money = render_money(pv["value"], unit_scale, currency)
                pages = (pv["page"],) if pv.get("page") else ()
                amount = pv["value"] * unit_scale
                put(TruthEntry(key, money, "ok", None, direction, pv["value"], amount, pages))
    for period in ratios.periods:
        change = into.get(period.period_id)
        for name, ratio in period.ratios.model_dump().items():
            key = f"ratio:{name}:{period.period_id}"
            if ratio["status"] != "ok" and ratio["value"] is None:
                reason = ratio["reason"] or ratio["status"]
                put(TruthEntry(key, None, "null", reason, None))
                continue
            rendered = render_ratio(ratio["value"], ratio["unit"])
            if "negative_denominator" in ratio["flags"]:
                rendered += " (not meaningful: negative denominator)"
            direction = None
            if change is not None and change.ratios[name].value is not None:
                direction = _direction(_round(_dec(change.ratios[name].value), _places(name)))
            put(TruthEntry(key, rendered, "ok", None, direction, ratio["value"]))
    for change in ratios.changes:
        span = f"{change.from_period_id}:{change.to_period_id}"
        for name, rc in change.ratios.items():
            key = f"change:ratio:{name}:{span}"
            if rc.value is None:
                put(TruthEntry(key, None, "null", "missing_input", None))
                continue
            rounded = _round(_dec(rc.value), _places(name))
            text = (
                render_point_change(rc.value)
                if rc.kind == "percentage_points"
                else render_multiple_change(rc.value)
            )
            put(TruthEntry(key, text, "ok", None, _direction(rounded)))
        for item_id, ic in change.items.items():
            key = f"change:item:{item_id}:{span}"
            if ic.absolute is None:
                put(TruthEntry(key, None, "null", "missing_input", None))
            elif ic.percent is None:  # a zero base: show the absolute change, not a percentage
                if unit_scale is None:
                    put(TruthEntry(key, None, "null", "unit_unknown", None))
                else:
                    text = ("+" if ic.absolute > 0 else "") + render_money(
                        ic.absolute, unit_scale, currency
                    )
                    put(TruthEntry(key, text, "ok", None, _direction(_dec(ic.absolute))))
            else:
                rounded = _round(_dec(ic.percent), 1)
                put(
                    TruthEntry(
                        key, render_percent_change(ic.percent), "ok", None, _direction(rounded)
                    )
                )
    for fact in facts.facts if facts else ():
        put(_fact_entry(fact))
    return truth


def _fact_entry(fact: SupplementalFact) -> TruthEntry:
    """A supplemental fact as a placeholder: `fact:<id>:<period>`. Null stays null."""
    key = f"fact:{fact.id}:{fact.period_id}"
    if fact.value is None:
        return TruthEntry(key, None, "null", "conflicting_sources", None)
    if fact.per_share:
        symbol = SYMBOLS.get(fact.currency or "", "")
        rendered = f"{symbol}{_round(_dec(fact.value), 2)}"
        amount = fact.value
    else:
        rendered = render_money(fact.value, fact.unit_scale, fact.currency)
        amount = fact.value * fact.unit_scale
    pages = tuple(sorted({s.page for s in fact.sources}))
    note = "non-GAAP measure" if fact.is_apm else None
    return TruthEntry(key, rendered, "ok", None, None, fact.value, amount, pages, note)


def _places(ratio_name: str) -> int:
    """Decimals shown for a ratio change: pp to one place, multiples to two."""
    return 1 if ratio_name in {"operating_margin", "roce"} else 2


def placeholders(text: str) -> list[str]:
    return [m.group(1) for m in PLACEHOLDER.finditer(text)]


def render_template(template: str, truth: Mapping[str, TruthEntry]) -> str:
    """Replace each known placeholder with its rendered text; an unknown one is left as written
    (validator V4 rejects such a paragraph before it is ever shown)."""

    def sub(match: re.Match[str]) -> str:
        entry = truth.get(match.group(1))
        return entry.text() if entry is not None else match.group(0)

    return PLACEHOLDER.sub(sub, template)
