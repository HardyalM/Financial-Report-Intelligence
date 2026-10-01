"""Human claim ratings (EVAL 4): the tech lead rates; the check is arithmetic.

Two shapes are read, per displayed paragraph (`<topic>:<n>`, from the artefact's `claims`):

- `{"id": ..., "rating": "supported" | "unsupported" | "contradicted"}`
- `{"paragraph_id": ..., "faithful": bool, "cited": bool, "notes": ...}` (the tech lead's form).
  Rule: faithful and cited is `supported`; anything else is `unsupported`. `contradicted` is never
  derived from two booleans: only an explicit `rating: "contradicted"` counts as one. A paragraph
  whose notes say the cited page does not state the claim is unsupported, not contradicted.

A rating file is complete only when its status is `rated` and every displayed paragraph is rated
exactly once. Nothing here invents a rating: a file that is not rated, or is incomplete, is not
complete, and the share is computed over the paragraphs that were rated.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

RATINGS = ("supported", "unsupported", "contradicted")


def rating_of(item: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """(paragraph id, rating) for one item in either shape; None where it cannot be read."""
    pid = item.get("id") or item.get("paragraph_id")
    if item.get("rating") in RATINGS:
        return pid, str(item["rating"])
    if isinstance(item.get("faithful"), bool) and isinstance(item.get("cited"), bool):
        return pid, "supported" if item["faithful"] and item["cited"] else "unsupported"
    return pid, None


def score_ratings(
    ratings: Mapping[str, Any] | None, displayed_ids: Collection[str]
) -> dict[str, Any]:
    read = [rating_of(i) for i in (ratings or {}).get("items", [])]
    rated = [(pid, r) for pid, r in read if pid is not None and r is not None]
    ids = [pid for pid, _ in rated]
    expected = set(displayed_ids)
    complete = (
        (ratings or {}).get("status") == "rated"
        and bool(expected)
        and set(ids) == expected
        and len(ids) == len(set(ids))
    )
    total = len(rated)
    return {
        "complete": complete,
        "total": total,
        "supported": sum(1 for _, r in rated if r == "supported") / total if total else 0.0,
        "unsupported": sorted(pid for pid, r in rated if r == "unsupported"),
        "contradicted": sum(1 for _, r in rated if r == "contradicted"),
        "unrated": sorted(expected - set(ids)),
    }
