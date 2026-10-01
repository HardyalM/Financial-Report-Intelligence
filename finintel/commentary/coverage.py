"""E8 coverage (EVAL 3.6): did the displayed commentary cover the facts the tech lead listed?

Label shape (the tech lead's): `principal_risks` and `key_audit_matters` items `{name, pages}`; a
`going_concern` block `{conclusion, pages, ...}`; optional `must_not_claim`.

- Recall: an item is covered when a displayed paragraph mentions it (at least MENTION_SHARE of the
  name's content words, parentheticals dropped, in the paragraph text or its quotes) and cites a
  chunk on or within PAGE_TOLERANCE pages of one of the item's listed pages.
- Going concern: the governance topic displays a paragraph about going concern citing on or near the
  listed pages, and no claim against the label appears outside a verified quotation. When the label
  has no `must_not_claim`, "material uncertainty" counts as a claim if the conclusion says none was
  identified; an explicit negation ("no", "not", "without", "absence of") before it is not a claim.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from finintel.commentary.validators.text import blank_verified_quotes
from finintel.contracts.commentary import Commentary, Paragraph
from finintel.evals.e3 import uses_printed_pages
from finintel.retrieval.lexical import terms

PAGE_TOLERANCE = 2
MENTION_SHARE = 0.6
_NEGATION = re.compile(r"\b(?:no|not|without|absence of|nor)\W+(?:\w+\W+){0,2}$", re.IGNORECASE)


def _shift(labels: Mapping[str, Any], folio_offset: int | None) -> int:
    if not uses_printed_pages(labels):
        return 0
    if folio_offset is None:
        raise ValueError("labels use printed pages but the document has no folio offset")
    return folio_offset


def _paragraph_text(para: Paragraph) -> str:
    return " ".join([para.rendered, *(c.quote for c in para.citations)])


def _mentions(para: Paragraph, name: str) -> bool:
    wanted = set(terms(re.sub(r"\([^)]*\)", " ", name)))
    if not wanted:
        return False
    present = set(terms(_paragraph_text(para)))
    return len(wanted & present) >= math.ceil(MENTION_SHARE * len(wanted))


def _near(para: Paragraph, pages: Sequence[int]) -> bool:
    return any(
        c.page - PAGE_TOLERANCE <= p <= c.page_end + PAGE_TOLERANCE
        for c in para.citations
        for p in pages
    )


def _pages(item: Mapping[str, Any], shift: int) -> list[int]:
    raw = item.get("pages") or [item["page"]]
    return [int(p) + shift for p in raw]


def _recall(
    items: Sequence[Mapping[str, Any]], paras: list[Paragraph], shift: int
) -> dict[str, Any]:
    missing = [
        item["name"]
        for item in items
        if not any(_mentions(p, item["name"]) and _near(p, _pages(item, shift)) for p in paras)
    ]
    total = len(items)
    return {
        "total": total,
        "found": total - len(missing),
        "missing": missing,
        "recall": (total - len(missing)) / total if total else 1.0,
    }


def _claims(text: str, phrases: Sequence[str]) -> list[str]:
    found = []
    lowered = text.lower()
    for phrase in phrases:
        for m in re.finditer(re.escape(phrase.lower()), lowered):
            if not _NEGATION.search(lowered[: m.start()][-40:]):
                found.append(phrase)
                break
    return found


def score_coverage(
    labels: Mapping[str, Any], commentary: Commentary, folio_offset: int | None
) -> dict[str, Any]:
    shift = _shift(labels, folio_offset)
    paras = [p for t in commentary.topics for p in t.paragraphs]
    risks = _recall(list(labels.get("principal_risks", [])), paras, shift)
    kams = _recall(list(labels.get("key_audit_matters", [])), paras, shift)
    going = labels.get("going_concern", {})
    governance = next((t for t in commentary.topics if t.topic == "governance_and_directors"), None)
    gov_paras = governance.paragraphs if governance else []
    listed = _pages(going, shift) if going else []
    about = any(
        "going concern" in _paragraph_text(p).lower() and (not listed or _near(p, listed))
        for p in gov_paras
    )
    phrases = list(labels.get("must_not_claim", []))
    if not phrases and "no material uncertainty" in str(going.get("conclusion", "")).lower():
        phrases = ["material uncertainty"]
    claimed: list[str] = []
    for p in gov_paras:
        outside = blank_verified_quotes(p.rendered, [c.quote for c in p.citations])
        claimed += _claims(outside, phrases)
    return {
        "risk_recall": risks["recall"],
        "kam_recall": kams["recall"],
        "risks": risks,
        "kams": kams,
        "going_concern_correct": bool(about and not claimed),
        "going_concern_claims_against_label": sorted(set(claimed)),
    }
