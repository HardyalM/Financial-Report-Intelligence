"""Human claim ratings (EVAL 4): the tech lead rates; the check is arithmetic.

`ratings.json`: `{"status": "rated", "items": [{"id": "<topic>:<n>", "rating": "supported" |
"unsupported" | "contradicted"}]}`. Ids are the displayed-paragraph ids written to the commentary
artefact. A rating file is complete only when every displayed paragraph is rated exactly once.
Nothing here invents a rating: a file that is not rated, or that is incomplete, is not complete.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

RATINGS = ("supported", "unsupported", "contradicted")


def score_ratings(
    ratings: Mapping[str, Any] | None, displayed_ids: Collection[str]
) -> dict[str, Any]:
    items = list((ratings or {}).get("items", []))
    rated = [i for i in items if i.get("rating") in RATINGS]
    ids = [i.get("id") for i in rated]
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
        "supported": sum(1 for i in rated if i["rating"] == "supported") / total if total else 0.0,
        "contradicted": sum(1 for i in rated if i["rating"] == "contradicted"),
        "unrated": sorted(expected - set(ids)),
    }
