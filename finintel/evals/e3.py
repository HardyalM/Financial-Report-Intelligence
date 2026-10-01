"""E3 retrieval: does the top 8 for each labelled query cover an expected page? (EVAL 3.3)

Labels are read, never written. `page_basis` in the label file says whether pages are printed
folios or PDF indices (see `uses_printed_pages`); folios are converted
with the document's own inferred offset, and the offset used is recorded in the report. A query
hits when any retrieved chunk's page range touches an expected page.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from finintel.narrative.models import Chunk

TOP_N = 8

Retrieve = Callable[[str], Sequence[str]]  # query -> chunk ids, best first


def uses_printed_pages(labels: Mapping[str, Any]) -> bool:
    """PDF indices when the basis names PDF or viewer pages (even if it also says "not printed");
    printed folios only when it names printed pages and neither of those."""
    basis = str(labels.get("page_basis", "")).lower()
    if "pdf" in basis or "viewer" in basis:
        return False
    return "printed" in basis


def compare(
    labels: Mapping[str, Any],
    chunks: Sequence[Chunk],
    retrieve: Retrieve,
    *,
    folio_offset: int | None,
    models: Mapping[str, str],
) -> dict[str, Any]:
    by_id = {c.chunk_id: c for c in chunks}
    printed = uses_printed_pages(labels)
    if printed and folio_offset is None:
        raise ValueError("labels use printed pages but the document has no inferable folio offset")
    cells: list[dict[str, Any]] = []
    for q in labels["queries"]:
        want_labelled = [int(p) for p in q["must_include_page_any_of"]]
        want = (
            [p + folio_offset for p in want_labelled] if printed and folio_offset else want_labelled
        )
        got = [by_id[cid] for cid in list(retrieve(q["q"]))[:TOP_N]]
        pages = sorted({p for c in got for p in range(c.page_start, c.page_end + 1)})
        hit = bool(set(want) & set(pages))
        cells.append(
            {
                "q": q["q"],
                "expected_labelled": want_labelled,
                "expected_pdf_pages": want,
                "retrieved": [
                    {
                        "chunk_id": c.chunk_id,
                        "pdf_pages": [c.page_start, c.page_end],
                        "section": c.section_id,
                        "heading_path": list(c.heading_path),
                    }
                    for c in got
                ],
                "hit": hit,
            }
        )
    hits = sum(1 for c in cells if c["hit"])
    return {
        "queries": len(cells),
        "hits": hits,
        "hit_at_8": hits / len(cells) if cells else 0.0,
        "page_basis": "printed" if printed else "pdf",
        "folio_offset": folio_offset,
        "models": dict(models),
        "cells": cells,
    }
