"""Override semantics (EXTRACTION section 6). Pure functions over a pack dict, plus the anchor test."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from finintel.parse.text_layer import TextLayer
from finintel.reconcile.pack import LIABILITY_ITEMS
from finintel.tables.numbers import parse_number

VALUE_ACTIONS = ("set_value", "accept_candidate")
DOCUMENT_TYPES = ("corporate", "bank", "nhs_trust", "other")


class OverrideError(Exception):
    """A refused override. `status` is the HTTP status the API answers with."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.status, self.code, self.message = status, code, message


@dataclass(frozen=True)
class ValueOverride:
    item: str
    period_id: str
    value: float | None  # None: set_null
    raw_text: str | None
    page: int | None
    anchored: bool
    reason: str | None = None


def anchored_on_page(layer: TextLayer, page: int, raw_text: str) -> bool:
    """`raw_text` is printed on `page`: its words are a contiguous run of the page's words."""
    target = raw_text.split()
    if not target:
        return False
    for p in layer.pages:
        if p.page != page:
            continue
        words = [w.text for w in p.words]
        return any(
            words[i : i + len(target)] == target for i in range(len(words) - len(target) + 1)
        )
    return False


def check_value(item: str, value: float, raw_text: str) -> None:
    """The value must be the number the printed text reads as, in the item's canonical sign: the
    same digits, and the printed sign except for a liability, which is stored as a positive
    magnitude even when printed in brackets (SCHEMA section 4.2, the extractor's own rule)."""
    parsed = parse_number(raw_text)
    if parsed is None or parsed.nil:
        raise OverrideError(422, "raw_text_not_a_number", f"{raw_text!r} is not a printed figure")
    # The extractor's rule (reconcile.pack._signed): a liability is the magnitude of what is printed.
    expected = float(abs(parsed.value) if item in LIABILITY_ITEMS else parsed.value)
    if abs(expected - value) > 1e-9 * max(1.0, abs(value)):
        how = f"{expected} for {item}" if expected != float(parsed.value) else f"{expected}"
        raise OverrideError(
            422, "value_does_not_match_raw_text", f"{raw_text!r} reads as {how}, not {value}"
        )


def apply_value_override(pack: Mapping[str, Any], ov: ValueOverride) -> dict[str, Any]:
    """A new pack with one value replaced by the person's, engine `human_override[_unanchored]`."""
    out: dict[str, Any] = copy.deepcopy(dict(pack))
    item = out["items"].get(ov.item)
    if item is None:
        raise OverrideError(422, "unknown_item", f"{ov.item!r} is not an item of this pack")
    entry = next((v for v in item["values"] if v["period_id"] == ov.period_id), None)
    if entry is None:
        raise OverrideError(422, "unknown_period", f"{ov.period_id!r} is not a period of this pack")
    engine = "human_override" if ov.anchored else "human_override_unanchored"
    for key in ("bbox", "derived_from", "derivation"):
        entry.pop(key, None)
    entry.update(
        value=ov.value, raw_text=ov.raw_text, page=ov.page, confidence=1.0, engine=engine,
        page_label=None,
    )  # fmt: skip
    code = "human_override" if ov.anchored else "human_override_unanchored"
    what = "set to null" if ov.value is None else f"set from p.{ov.page}"
    out["warnings"] = [
        *out.get("warnings", []),
        {"code": code, "message": f"{ov.item} {ov.period_id} {what} by a person"
         + (f": {ov.reason}" if ov.reason else ""), "item": ov.item, "page": ov.page},
    ]  # fmt: skip
    return out


def apply_document_type(
    pack: Mapping[str, Any], document_type: str, reason: str | None
) -> dict[str, Any]:
    """A person's document-type decision. The ratio engine re-applies its applicability matrix."""
    if document_type not in DOCUMENT_TYPES:
        raise OverrideError(422, "unknown_document_type", f"{document_type!r}")
    out: dict[str, Any] = copy.deepcopy(dict(pack))
    out["document_type"] = document_type
    out["warnings"] = [
        w for w in out.get("warnings", []) if w.get("code") != "document_type_ambiguous"
    ]
    return out


def materialise(pack: Mapping[str, Any], overrides: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Re-apply stored overrides, in order, to a (re-)extracted pack. Each is a row of `overrides`
    as `{action, anchored, reason, payload}`; location and unit actions act at extraction."""
    out: dict[str, Any] = dict(pack)
    for row in overrides:
        payload = row["payload"]
        if row["action"] in (*VALUE_ACTIONS, "set_null"):
            out = apply_value_override(
                out,
                ValueOverride(
                    item=payload["item"], period_id=payload["period_id"],
                    value=payload.get("value"), raw_text=payload.get("raw_text"),
                    page=payload.get("page"), anchored=bool(row["anchored"]), reason=row.get("reason"),
                ),
            )  # fmt: skip
        elif row["action"] == "document_type":
            out = apply_document_type(out, payload["document_type"], row.get("reason"))
    return out
