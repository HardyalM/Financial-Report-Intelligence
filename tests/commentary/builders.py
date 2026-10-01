"""Canned chunks and packs for the offline commentary tests (no model, no network)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from finintel.commentary.render import TruthEntry, build_ground_truth
from finintel.narrative import CHUNKER_VERSION
from finintel.narrative.models import Chunk, LineBox
from finintel.ratios import compute_ratios

ROOT = Path(__file__).resolve().parents[2]
RISK = (
    "Management identifies supply chain disruption as a principal risk, noting exposure to "
    "single-source suppliers for key categories remains elevated across the group."
)
Q_RISK = "exposure to single-source suppliers for key categories remains elevated"


def chunk(
    cid: str,
    text: str,
    *,
    page: int = 57,
    page_end: int | None = None,
    breaks: Sequence[tuple[int, int]] = (),
    section: str = "principal_risks",
    char_start: int = 1000,
    note_number: str | None = None,
    boxes: Sequence[LineBox] | None = None,
) -> Chunk:
    page_map = ((0, page), *breaks)
    default_box = LineBox(offset=0, page=page, bbox=(50, 100, 500, 112))
    return Chunk(
        chunk_id=cid,
        chunker_version=CHUNKER_VERSION,
        document_sha256="ab" * 32,
        text=text,
        token_count=len(text.split()),
        char_start=char_start,
        char_end=char_start + len(text),
        page_start=page,
        page_end=page_end or (breaks[-1][1] if breaks else page),
        char_page_map=page_map,
        line_boxes=tuple(boxes) if boxes is not None else (default_box,),
        section_id=section,
        heading_path=("Strategic report", "Principal risks"),
        note_number=note_number,
    )  # fmt: skip


def evidence(*chunks: Chunk) -> dict[str, Chunk]:
    return {c.chunk_id: c for c in chunks}


def company_pack() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (ROOT / "fixtures" / "expected" / "company_a.json").read_text(encoding="utf-8")
    )
    return data


def truth_for(pack: Mapping[str, Any] | None = None) -> dict[str, TruthEntry]:
    pack = pack or company_pack()
    return build_ground_truth(pack, compute_ratios(pack))


def raw(
    paragraphs: Sequence[Mapping[str, Any]],
    *,
    topic: str = "strategic_risks",
    status: str = "ok",
    reason: str | None = None,
) -> dict[str, Any]:
    return {"topic": topic, "status": status, "reason": reason, "paragraphs": list(paragraphs)}


def para(template: str, *citations: tuple[str, str]) -> dict[str, Any]:
    return {"template": template, "citations": [{"chunk_id": c, "quote": q} for c, q in citations]}
