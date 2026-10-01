"""Chunk records (RAG section 2). Citations are built from these, so offsets must be exact."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

#: Semantic version of the chunking rules. Part of every chunk_id: changing the rules changes all
#: ids, which marks stored commentary stale so citations never point at vanished chunks.
CHUNKER_VERSION = "1.1.0"

TARGET_MIN_TOKENS = 300
TARGET_MAX_TOKENS = 450
HARD_MAX_TOKENS = 600
SMALL_SECTION_TOKENS = 80

BBox = tuple[float, float, float, float]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LineBox(_Frozen):
    """One printed line inside a chunk: where it starts in the chunk text, and where it sits."""

    offset: int  # character offset in the chunk text
    page: int  # 1-based PDF page
    bbox: BBox  # display-space points on that page, for highlighting


class Chunk(_Frozen):
    chunk_id: str
    chunker_version: str
    document_sha256: str
    text: str  # normalised whitespace; the exact string quotes are verified against
    token_count: int
    char_start: int  # offsets in the document's narrative text (chunks joined by a blank line)
    char_end: int
    page_start: int
    page_end: int
    char_page_map: tuple[tuple[int, int], ...]  # (offset in chunk text, page): a run starts here
    line_boxes: tuple[LineBox, ...]
    section_id: str
    heading_path: tuple[str, ...]
    sub_headings: tuple[str, ...] = ()
    is_note: bool = False
    note_number: str | None = None
    note_title: str | None = None
    is_footnote: bool = False
    footnote_marker: str | None = None
    is_table: bool = False  # stored atomic, never embedded in v1

    def page_at(self, offset: int) -> int:
        """The PDF page holding character `offset` of this chunk's text (for citations)."""
        if not 0 <= offset < max(len(self.text), 1):
            raise IndexError(f"offset {offset} outside the chunk text")
        page = self.char_page_map[0][1]
        for start, candidate in self.char_page_map:
            if start > offset:
                break
            page = candidate
        return page
