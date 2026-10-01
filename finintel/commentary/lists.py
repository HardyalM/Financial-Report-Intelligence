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
from finintel.commentary.render import PLACEHOLDER, TruthEntry, render_template
from finintel.commentary.validators import finalize, mismatched_placeholders, validate_output
from finintel.contracts.commentary import Figure, Paragraph, ParagraphValidation
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


_GOING_CONCERN = re.compile(r"^going concern$", re.IGNORECASE)


def going_concern_bullets(
    retrieved_ids: Sequence[str],
    chunks: Sequence[Chunk],
    truth: Mapping[str, TruthEntry],
    page_labels: Mapping[int, str] | None = None,
) -> list[Paragraph]:
    """One code-built bullet for each passage headed exactly "Going concern" (the directors'
    statement, the accounting-policy note). The pages are found by heading, never named, and no
    model writes the bullet. If no such passage was retrieved for the topic, there is no bullet."""
    by_id = {c.chunk_id: c for c in chunks}
    anchored = any(
        _GOING_CONCERN.match(by_id[i].heading_path[-1].strip())
        or by_id[i].section_id == "going_concern"
        for i in retrieved_ids
        if i in by_id
    )
    if not anchored:
        return []
    bullets: list[Paragraph] = []
    seen: set[tuple[str, ...]] = set()
    for chunk in _prose(chunks):
        if not _GOING_CONCERN.match(chunk.heading_path[-1].strip()) or chunk.heading_path in seen:
            continue
        group = [c for c in _prose(chunks) if c.heading_path == chunk.heading_path]
        sentences = [(c, opening_sentences(c.text)) for c in group]
        pick = next(((c, s) for c, s in sentences if s and "going concern" in s.lower()), None)
        pick = pick or next(((c, s) for c, s in sentences if s), None)
        if pick is None:
            continue
        holder, sentence = pick
        raw = {
            "topic": "governance_and_directors", "status": "ok", "reason": None,
            "paragraphs": [{
                "template": f"Going concern: \u201c{sentence}\u201d",
                "citations": [{"chunk_id": holder.chunk_id, "quote": sentence}],
            }],
        }  # fmt: skip
        report = validate_output(
            raw, topic="governance_and_directors", evidence={holder.chunk_id: holder},
            truth=truth, page_labels=page_labels,
        )  # fmt: skip
        kept = finalize(report, retried=False)[2]
        if kept:
            bullets.append(kept[0])
            seen.add(chunk.heading_path)
    return bullets


# --------------------------------------------------------------- liquidity and capital

_ROIC = re.compile(r"return on invested capital|\bROIC\b", re.IGNORECASE)
_PERCENT = re.compile(r"\d+(?:\.\d+)?%")
_SENTENCES = re.compile(r"(?<=[.!?])\s+(?=[A-Z\u201c\"(])")


def _sentences(chunk: Chunk) -> list[str]:
    return [" ".join(s.split()) for s in _SENTENCES.split(chunk.text.strip())]


def _quotable(sentence: str) -> bool:
    words = len(sentence.split())
    return 5 <= words <= 60 and '"' not in sentence and "\u201c" not in sentence


def _figure_paragraph(template: str, truth: Mapping[str, TruthEntry]) -> Paragraph | None:
    """A bullet made only of placeholders and plain words, with each figure's own source page(s).
    None if any figure is unavailable or has no page: the bullet is then not shown."""
    keys = list(dict.fromkeys(m.group(1) for m in PLACEHOLDER.finditer(template)))
    if any(k not in truth or truth[k].rendered is None or not truth[k].pages for k in keys):
        return None
    if mismatched_placeholders(template, truth):
        return None
    return Paragraph(
        template=template,
        rendered=render_template(template, truth),
        citations=[],
        figures=[
            Figure(placeholder=k, rendered=truth[k].rendered, pages=sorted(truth[k].pages))
            for k in keys
        ],
        validation=ParagraphValidation(retried=False, removed_citations=[]),
    )


def roic_bullet(
    chunks: Sequence[Chunk],
    truth: Mapping[str, TruthEntry],
    page_labels: Mapping[int, str] | None = None,
) -> Paragraph | None:
    """The report's own underlying return on invested capital, quoted and not computed.

    The sentence that states it and the one that defines it; each quote is verified and cited."""
    prose = [c for c in _prose(chunks) if c.section_id not in EXCLUDED_FOR_RETURN]
    stated = defined = None
    for chunk in prose:
        for sentence in _sentences(chunk):
            low = sentence.lower()
            if not (_quotable(sentence) and _ROIC.search(sentence)):
                continue
            if stated is None and "underlying" in low and _PERCENT.search(sentence):
                stated = (chunk, sentence)
            elif defined is None and "is calculated as" in low:
                defined = (chunk, sentence)
        if stated and defined:
            break
    if stated is None:
        return None
    picks = [stated, *([defined] if defined else [])]
    template = (
        "Underlying return on invested capital, as the report states it (quoted, not computed): "
        f"\u201c{stated[1]}\u201d"
    )
    if defined:
        template += f" The report defines it: \u201c{defined[1]}\u201d"
    raw = {
        "topic": "liquidity_and_capital", "status": "ok", "reason": None,
        "paragraphs": [{
            "template": template,
            "citations": [{"chunk_id": c.chunk_id, "quote": q} for c, q in picks],
        }],
    }  # fmt: skip
    report = validate_output(
        raw, topic="liquidity_and_capital", evidence={c.chunk_id: c for c, _ in picks},
        truth=truth, page_labels=page_labels,
    )  # fmt: skip
    kept = finalize(report, retried=False)[2]
    return kept[0] if kept else None


#: Sections whose "return on invested capital" is a remuneration target, not the company's result.
EXCLUDED_FOR_RETURN = frozenset({"remuneration_report", "notes_other"})


def liquidity_bullets(
    period_id: str,
    truth: Mapping[str, TruthEntry],
    chunks: Sequence[Chunk],
    page_labels: Mapping[int, str] | None = None,
) -> list[Paragraph]:
    """The liquidity and capital topic, built by code. No model writes it.

    Balance-sheet lines and the current ratio computed from them (labelled computed), each citing
    the page that prints its inputs; and the report's own return on invested capital, quoted. A
    bullet whose figures are unavailable is omitted. ROCE is not shown (the report never prints it).
    """
    p = period_id
    templates = [
        f"Current assets were {{{{exact:current_assets:{p}}}}} and current liabilities were "
        f"{{{{exact:current_liabilities:{p}}}}} on the consolidated balance sheet.",
        "Current ratio, computed in code from current assets and current liabilities "
        "(the ratio is not printed in the report): "
        f"{{{{exact:current_assets:{p}}}}} / {{{{exact:current_liabilities:{p}}}}} = "
        f"{{{{ratio:current_ratio:{p}}}}}.",
        f"Total equity, including non-controlling interests, was {{{{exact:total_equity:{p}}}}} "
        f"on the consolidated balance sheet.",
    ]
    bullets = [b for t in templates if (b := _figure_paragraph(t, truth)) is not None]
    roic = roic_bullet(chunks, truth, page_labels)
    return [*bullets, *([roic] if roic is not None else [])]
