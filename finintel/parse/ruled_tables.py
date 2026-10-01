"""Ruled-table boxes from PyMuPDF `find_tables` (lines strategy), cached per document.

An independent signal beside the narrative chunker's own numeric-density detector: boxed tables
that print their figures under rules are found here even when the figures are percentages or
sparse. Regions are display-space points per 1-based PDF page.
"""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf

from finintel.cache import StageCache, StageKey
from finintel.parse.text_layer import BBox

RULED_VERSION = "1"


def ruled_tables(pdf: Path, sha256: str, cache: StageCache) -> dict[int, list[BBox]]:
    """PyMuPDF `find_tables` (ruled strategy) boxes per page, cached per document and version."""
    key = StageKey.build(
        sha256, "pymupdf_ruled_tables", RULED_VERSION, {"pymupdf": str(pymupdf.VersionBind)}
    )

    def compute() -> bytes:
        found: dict[str, list[BBox]] = {}
        with pymupdf.open(pdf) as doc:
            for number in range(1, doc.page_count + 1):
                boxes = [
                    (
                        round(t.bbox[0], 2),
                        round(t.bbox[1], 2),
                        round(t.bbox[2], 2),
                        round(t.bbox[3], 2),
                    )
                    for t in doc[number - 1].find_tables(strategy="lines").tables
                ]
                if boxes:
                    found[str(number)] = boxes
        return json.dumps(found).encode("utf-8")

    data, _ = cache.memo(key, "regions.json", compute)
    return {int(p): [tuple(b) for b in boxes] for p, boxes in json.loads(data).items()}
