"""Evidence-driven lists: one bullet per key audit matter, one per principal risk (M5.2).

Both lists come from the document's own structure and text, never from a label file:

- Key audit matters: the numbered sub-headings ("4.1 Revenue recognition ...") under the auditor's
  "Key audit matters" heading. Each matter becomes a bullet built by code: its title and the first
  quotable sentence of its own section, cited at its own page. No model is involved.
- Principal risks: the chunks under the principal-risks heading, handed to the model with the
  instruction to name each distinct risk the text describes and quote its own passage. Every bullet
  passes V1-V8 and cites a chunk of that section, so a risk the model cannot quote is dropped.

Both are anchored on retrieval: a list is produced only if a retrieved chunk for the topic lies in
the relevant section. If the section was not retrieved, no list, and the ordinary topic path runs.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from finintel.commentary.extractive import opening_sentences
from finintel.commentary.render import TruthEntry
from finintel.commentary.validators import finalize, validate_output
from finintel.contracts.commentary import Paragraph
from finintel.narrative.models import Chunk

MAX_LIST_BULLETS = 20
_KAM_ROOT = re.compile(r"^(?P<num>\d+)\.\s*key audit matters?\b", re.IGNORECASE)
_CONTINUED = re.compile(r"\s*[\-\u2013:]?\s*\(?continued\)?\s*$", re.IGNORECASE)


def _prose(chunks: Sequence[Chunk]) -> list[Chunk]:
    return sorted((c for c in chunks if not c.is_table), key=lambda c: c.char_start)


def kam_groups(chunks: Sequence[Chunk]) -> list[tuple[str, list[Chunk]]]:
    """(title, chunks) per numbered key audit matter, in document order."""
    ordered = _prose(chunks)
    start = next(
        (i for i, c in enumerate(ordered) if _KAM_ROOT.match(c.heading_path[-1].strip())), None
    )
    if start is None:
        return []
    number = _KAM_ROOT.match(ordered[start].heading_path[-1].strip())
    assert number is not None
    sub = re.compile(rf"^{number.group('num')}\.\d+\s+(?P<title>\S.*)$")
    groups: list[tuple[str, list[Chunk]]] = []
    for chunk in ordered[start + 1 :]:
        leaf = chunk.heading_path[-1].strip()
        match = sub.match(leaf)
        if match is None:
            if re.match(r"^\d+\.\s", leaf):  # the next top-level section of the report
                break
            continue
        title = _CONTINUED.sub("", match.group("title")).strip()
        if groups and groups[-1][0] == title:
            groups[-1][1].append(chunk)
        else:
            groups.append((title, [chunk]))
    return groups


def kam_bullets(
    retrieved_ids: Sequence[str],
    chunks: Sequence[Chunk],
    truth: Mapping[str, TruthEntry],
    page_labels: Mapping[int, str] | None = None,
) -> list[Paragraph]:
    """One bullet per key audit matter, if the auditor's report was retrieved for the topic."""
    by_id = {c.chunk_id: c for c in chunks}
    if not any(by_id[i].section_id == "auditors_report" for i in retrieved_ids if i in by_id):
        return []
    bullets: list[Paragraph] = []
    for title, group in kam_groups(chunks)[:MAX_LIST_BULLETS]:
        for chunk in group:
            sentence = opening_sentences(chunk.text)
            if sentence is None:
                continue
            raw = {
                "topic": "governance_and_directors", "status": "ok", "reason": None,
                "paragraphs": [{
                    "template": f"Key audit matter: {title}. “{sentence}”",
                    "citations": [{"chunk_id": chunk.chunk_id, "quote": sentence}],
                }],
            }  # fmt: skip
            report = validate_output(
                raw, topic="governance_and_directors", evidence={chunk.chunk_id: chunk},
                truth=truth, page_labels=page_labels,
            )  # fmt: skip
            kept = finalize(report, retried=False)[2]
            if kept:
                bullets.append(kept[0])
                break
    return bullets


def risk_section(retrieved_ids: Sequence[str], chunks: Sequence[Chunk]) -> list[Chunk]:
    """All chunks under the principal-risks heading that retrieval landed in, in document order.
    Empty if no retrieved chunk is a principal-risks chunk."""
    by_id = {c.chunk_id: c for c in chunks}
    anchors = [
        by_id[i].heading_path
        for i in retrieved_ids
        if i in by_id and by_id[i].section_id == "principal_risks" and not by_id[i].is_note
    ]
    if not anchors:
        return []
    heading = max(set(anchors), key=anchors.count)
    return [c for c in _prose(chunks) if c.heading_path == heading]
