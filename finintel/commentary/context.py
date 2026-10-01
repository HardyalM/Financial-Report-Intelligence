"""Context expansion (RAG section 3.4): neighbours of the selected chunks within a token budget.

Neighbours are the previous and next chunk in document order that share the section and are not
tables. Every added chunk keeps its own `chunk_id`, so a citation can point at it. Selected chunks
are placed first, in rank order; neighbours only fill what is left of the budget.
"""

from __future__ import annotations

from collections.abc import Sequence

from finintel.narrative.models import Chunk

TOKEN_BUDGET = 3500


def expand_context(
    selected: Sequence[str], chunks: Sequence[Chunk], budget: int = TOKEN_BUDGET
) -> list[Chunk]:
    ordered = sorted(chunks, key=lambda c: c.char_start)
    position = {c.chunk_id: i for i, c in enumerate(ordered)}
    taken: dict[str, Chunk] = {}
    used = 0

    def add(chunk: Chunk, *, force: bool = False) -> None:
        nonlocal used
        if chunk.chunk_id in taken:
            return
        if not force and used + chunk.token_count > budget:
            return
        taken[chunk.chunk_id] = chunk
        used += chunk.token_count

    for rank, cid in enumerate(selected):
        add(ordered[position[cid]], force=rank == 0)  # the best chunk is never squeezed out
    for cid in selected:
        i = position[cid]
        for j in (i - 1, i + 1):
            if 0 <= j < len(ordered):
                near = ordered[j]
                if near.section_id == ordered[i].section_id and not near.is_table:
                    add(near)
    return sorted(taken.values(), key=lambda c: c.char_start)
