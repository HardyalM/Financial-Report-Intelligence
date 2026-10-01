"""Structure-aware chunking (RAG section 2, ADR-002).

Rules enforced here:
- a chunk lives inside one heading path and never crosses a heading;
- paragraphs are packed to 300-450 tokens (hard maximum 600); one paragraph over the maximum is
  split at sentence boundaries; tables are atomic, are never split and never share a chunk with
  prose; footnotes are their own small chunks;
- consecutive small sibling sections (each under 80 tokens, same parent) merge into one chunk that
  carries the parent's heading path and lists the sub-headings;
- every chunk records, per printed line, its page and box, so a quote's page is derived from its
  offset (a chunk can cross a page break) and never taken from the chunk's first page;
- the note number is a state machine that carries across page breaks until the next note heading.

The text of a chunk is verbatim printed text, lines joined by single spaces and paragraphs by a
blank line. Excluded sections (RAG section 1.2) and excluded pages produce no chunks.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import ceil

from finintel.locate.outline import section_paths
from finintel.locate.signals import normalise
from finintel.narrative.blocks import Block, LineRef, body_size, page_blocks
from finintel.narrative.margins import furniture
from finintel.narrative.models import (
    CHUNKER_VERSION,
    HARD_MAX_TOKENS,
    SMALL_SECTION_TOKENS,
    TARGET_MAX_TOKENS,
    TARGET_MIN_TOKENS,
    BBox,
    Chunk,
    LineBox,
)
from finintel.narrative.sections import EXCLUDED, classify, note_heading
from finintel.parse.text_layer import TextLayer

#: Fragments this short ("Towards net zero", a caption) are infographic furniture, not quotable.
MIN_PROSE_TOKENS = 6
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9“\"(])")
_FINANCIAL = re.compile(r"\bfinancial statements\b|\bnotes to\b|\baccounts\b")


def estimate_tokens(text: str) -> int:
    """Words x 1.3, rounded up: close enough to a BPE count to size chunks, with no tokenizer."""
    return max(1, ceil(len(text.split()) * 1.3))


@dataclass
class Para:
    text: str
    spans: list[tuple[int, int, LineRef]]  # (start, end) of each line in `text`

    @classmethod
    def from_block(cls, block: Block) -> Para:
        text, spans = "", []
        for line in block.lines:
            if text:
                text += " "
            spans.append((len(text), len(text) + len(line.text), line))
            text += line.text
        return cls(text, spans)

    def piece(self, start: int, end: int) -> Para:
        """The slice [start, end) with its lines, offsets shifted to the slice."""
        text = self.text[start:end].strip()
        lead = len(self.text[start:end]) - len(self.text[start:end].lstrip())
        spans = []
        for s, e, ref in self.spans:
            lo, hi = max(s, start + lead), min(e, start + lead + len(text))
            if hi > lo:
                spans.append((lo - start - lead, hi - start - lead, ref))
        return Para(text, spans)


@dataclass
class Run:
    kind: str  # prose, table, footnote
    path: tuple[str, ...]
    section_id: str
    note: tuple[str, str] | None
    paras: list[Para] = field(default_factory=list)
    marker: str | None = None
    sub_headings: list[str] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return sum(estimate_tokens(p.text) for p in self.paras)


def build_chunks(
    layer: TextLayer,
    *,
    document_sha256: str,
    excluded_pages: Mapping[int, str] | None = None,
    table_regions: Mapping[int, Sequence[BBox]] | None = None,
    chunker_version: str = CHUNKER_VERSION,
) -> list[Chunk]:
    """Chunk the narrative of a document. `excluded_pages` maps PDF pages to the section id that
    excludes them (the locator's primary-statement and company-statement pages); `table_regions`
    are external ruled-table boxes per page (display space) that join the density detector."""
    runs = _runs(layer, excluded_pages or {}, table_regions or {})
    runs = _merge_small(runs)
    return _emit(runs, document_sha256, chunker_version)


# ------------------------------------------------------------------------------ runs


def _runs(
    layer: TextLayer,
    excluded_pages: Mapping[int, str],
    external: Mapping[int, Sequence[BBox]],
) -> list[Run]:
    repeated, body = furniture(layer), body_size(layer)
    chains = section_paths(layer.outline, layer.page_count)
    first_bookmark = min((e.page for e in layer.outline if e.page), default=None)
    primary_roots = {
        chains[p][0] for p, s in excluded_pages.items() if s == "primary_statements" and chains[p]
    }
    # Parent-company accounts hang under their own bookmark root ("Unilever PLC Accounts"): the
    # locator found their statements, so everything under that root is company-only. A root shared
    # with the consolidated statements is never used.
    company_roots = {
        chains[p][0] for p, s in excluded_pages.items() if s == "company_statements" and chains[p]
    } - primary_roots
    runs: list[Run] = []
    current: Run | None = None
    stack: list[tuple[int, str]] = []
    note: tuple[str, str] | None = None
    previous_chain: tuple[str, ...] | None = None

    def flush() -> None:
        nonlocal current
        if current is not None and current.paras:
            runs.append(current)
        current = None

    def path_now(chain: tuple[str, ...]) -> tuple[str, ...]:
        out = list(chain)
        # Bookmarks are page-granular: when a note heading is seen on the page, the bookmark's own
        # note title may belong to a later note on the same page, so the printed heading wins.
        if out and note_heading(out[-1]) and any(note_heading(t) for _, t in stack):
            out.pop()
        for _, title in stack:
            if not out or normalise(out[-1]) != normalise(title):
                out.append(title)
        return tuple(out)

    def section_for(path: tuple[str, ...], page: int, chain: tuple[str, ...]) -> str:
        if page in excluded_pages:
            return excluded_pages[page]
        if path and path[0] in company_roots:
            return "company_statements"
        if first_bookmark is not None and page < first_bookmark and not chain and not path[1:]:
            return "front_matter"
        return classify(path)

    for page in layer.pages:
        number = page.page
        chain = chains[number]
        if chain != previous_chain:
            flush()
            stack = []
            previous_chain = chain
            if chain and _in_financial_statements(chain) and (nh := note_heading(chain[-1])):
                note = nh
        if number in excluded_pages:
            flush()
            continue
        blocks, _ = page_blocks(page, repeated, body, external.get(number, ()))
        for block in blocks:
            in_fs = _in_financial_statements(path_now(chain))
            if block.kind == "heading":
                nh = note_heading(block.text) if in_fs else None
                if nh and nh != note:
                    flush()  # a new note starts: what follows belongs to it
                    note = nh
                    stack = []  # a note heading is top level within the notes
                if _repeats_context(block.text, chain, stack):
                    continue  # a running title ("Note 11: ... continued"): same section
                flush()
                stack = [(lv, t) for lv, t in stack if lv < block.level]
                stack.append((block.level, block.text))
                continue
            path = path_now(chain)
            section = section_for(path, number, chain)
            if block.kind in ("table", "footnote"):
                if current is not None and block.kind == "table":
                    flush()
                run = Run(
                    "table" if block.kind == "table" else "footnote",
                    path, section, note if in_fs else None,
                    [Para.from_block(block)], block.marker,
                )  # fmt: skip
                runs.append(run)
                continue
            if current is None or current.path != path or current.section_id != section:
                flush()
                current = Run("prose", path, section, note if in_fs else None)
            current.paras.append(Para.from_block(block))
    flush()
    return [
        r
        for r in runs
        if r.section_id not in EXCLUDED and (r.kind != "prose" or r.tokens >= MIN_PROSE_TOKENS)
    ]


_TRAILING_CONTINUED = re.compile(r"\s*[\-\u2013:]?\s*\(?continued\)?\s*$", re.IGNORECASE)


def _repeats_context(text: str, chain: tuple[str, ...], stack: list[tuple[int, str]]) -> bool:
    """A heading that only repeats the current path, or repeats it with 'continued' added."""
    bare = normalise(_TRAILING_CONTINUED.sub("", text))
    known = {normalise(_TRAILING_CONTINUED.sub("", t)) for t in (*chain, *(t for _, t in stack))}
    return bare in known


def _in_financial_statements(path: Sequence[str]) -> bool:
    return any(_FINANCIAL.search(normalise(t)) for t in path)


def _merge_small(runs: list[Run]) -> list[Run]:
    """Consecutive small prose runs under one parent heading become one run (RAG section 2)."""
    out: list[Run] = []
    for run in runs:
        prev = out[-1] if out else None
        if (
            prev is not None
            and prev.kind == run.kind == "prose"
            and prev.tokens < SMALL_SECTION_TOKENS
            and run.tokens < SMALL_SECTION_TOKENS
            and len(prev.path) >= 2
            and prev.path[:-1] == run.path[:-1]
            and prev.path != run.path
            and prev.note == run.note
            and prev.tokens + run.tokens <= TARGET_MAX_TOKENS
        ):
            subs = prev.sub_headings or [prev.path[-1]]
            out[-1] = Run(
                "prose", prev.path[:-1], prev.section_id, prev.note, prev.paras + run.paras,
                sub_headings=[*subs, run.path[-1]],
            )  # fmt: skip
        else:
            out.append(run)
    return out


# ------------------------------------------------------------------------------ chunks


def _emit(runs: list[Run], sha: str, version: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    cursor = 0
    for run in runs:
        groups = [run.paras] if run.kind != "prose" else _pack(run.paras)
        for paras in groups:
            chunk = _chunk(run, paras, cursor, sha, version)
            chunks.append(chunk)
            cursor = chunk.char_end + 2  # chunks are joined by a blank line in the narrative text
    return chunks


def _pack(paras: list[Para]) -> list[list[Para]]:
    """Greedy packing to the token target; oversize paragraphs are split at sentences first."""
    flat: list[Para] = []
    for p in paras:
        flat.extend(_split(p) if estimate_tokens(p.text) > HARD_MAX_TOKENS else [p])
    groups: list[list[Para]] = []
    current: list[Para] = []
    size = 0
    for p in flat:
        t = estimate_tokens(p.text)
        fits = size + t <= TARGET_MAX_TOKENS or (
            size < TARGET_MIN_TOKENS and size + t <= HARD_MAX_TOKENS
        )
        if current and not fits:
            groups.append(current)
            current, size = [], 0
        current.append(p)
        size += t
    if current:
        groups.append(current)
    return groups


def _split(p: Para) -> list[Para]:
    """Split one long paragraph at sentence boundaries into pieces of at most the target size."""
    bounds = [0] + [m.end() for m in _SENTENCE.finditer(p.text)] + [len(p.text)]
    pieces: list[Para] = []
    start = 0
    for i in range(1, len(bounds)):
        if estimate_tokens(p.text[start : bounds[i]]) > TARGET_MAX_TOKENS and bounds[i - 1] > start:
            pieces.append(p.piece(start, bounds[i - 1]))
            start = bounds[i - 1]
    pieces.append(p.piece(start, len(p.text)))
    return [x for x in pieces if x.text]


def _chunk(run: Run, paras: list[Para], start: int, sha: str, version: str) -> Chunk:
    text = "\n\n".join(p.text for p in paras)
    boxes: list[LineBox] = []
    offset = 0
    for p in paras:
        for s, _, ref in p.spans:
            boxes.append(LineBox(offset=offset + s, page=ref.page, bbox=_round(ref.bbox)))
        offset += len(p.text) + 2
    mapping: list[tuple[int, int]] = []
    for box in boxes:
        if not mapping or mapping[-1][1] != box.page:
            mapping.append((box.offset if mapping else 0, box.page))
    pages = [b.page for b in boxes]
    number, title = run.note if run.note else (None, None)
    return Chunk(
        chunk_id=hashlib.sha256(f"{sha}:{version}:{start}".encode()).hexdigest()[:16],
        chunker_version=version,
        document_sha256=sha,
        text=text,
        token_count=estimate_tokens(text),
        char_start=start,
        char_end=start + len(text),
        page_start=min(pages),
        page_end=max(pages),
        char_page_map=tuple(mapping),
        line_boxes=tuple(boxes),
        section_id=run.section_id,
        heading_path=run.path,
        sub_headings=tuple(run.sub_headings),
        is_note=number is not None or run.section_id.startswith("notes"),
        note_number=number,
        note_title=title,
        is_footnote=run.kind == "footnote",
        footnote_marker=run.marker,
        is_table=run.kind == "table",
    )


def _round(box: BBox) -> BBox:
    return (round(box[0], 2), round(box[1], 2), round(box[2], 2), round(box[3], 2))
