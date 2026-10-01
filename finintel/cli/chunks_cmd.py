"""`finintel chunks <pdf|fixture> [--json]` (M4.1): the narrative chunks of a report.

Excluded pages come from the locator: the located primary statements (income statement, balance
sheet, cash flow, equity, comprehensive income) and every page it scopes to the parent company.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TextIO

from finintel.cache import StageCache
from finintel.cli.common import cached_text_layer, resolve_pdf
from finintel.ingest import ingest
from finintel.locate import LocateResult, Scope, locate
from finintel.narrative import Chunk, build_chunks
from finintel.parse.ruled_tables import ruled_tables


def excluded_pages(located: LocateResult) -> dict[int, str]:
    pages = {
        p: "primary_statements"
        for loc in located.statements.values()
        if loc.status == "found"
        for p in loc.pages
    }
    for c in located.candidates:
        if c.scope is Scope.COMPANY:
            pages[c.page] = "company_statements"
    return pages


def chunk_pdf(target: str, cache_dir: Path) -> tuple[Path, str, list[Chunk], dict[int, str]]:
    pdf = resolve_pdf(target)
    record = ingest(pdf)
    cache = StageCache(cache_dir)
    layer, _ = cached_text_layer(pdf, record.sha256, cache)
    excluded = excluded_pages(locate(layer))
    chunks = build_chunks(
        layer,
        document_sha256=record.sha256,
        excluded_pages=excluded,
        table_regions=ruled_tables(pdf, record.sha256, cache),
    )
    return pdf, record.sha256, chunks, excluded


def as_json(
    pdf: Path, sha256: str, chunks: list[Chunk], excluded: dict[int, str]
) -> dict[str, Any]:
    return {
        "file": pdf.name,
        "sha256": sha256,
        "excluded_pages": {str(p): s for p, s in sorted(excluded.items())},
        "chunks": [c.model_dump(mode="json") for c in chunks],
    }


def report(pdf: Path, chunks: list[Chunk], excluded: dict[int, str], out: TextIO) -> None:
    prose = [c for c in chunks if not c.is_table and not c.is_footnote]
    tokens = sorted(c.token_count for c in prose)
    by_section: dict[str, int] = {}
    for c in chunks:
        by_section[c.section_id] = by_section.get(c.section_id, 0) + 1
    print(
        f"{pdf.name}  {len(chunks)} chunks: {len(prose)} prose, "
        f"{sum(c.is_table for c in chunks)} table, {sum(c.is_footnote for c in chunks)} footnote",
        file=out,
    )
    if tokens:
        print(
            f"  prose tokens: min {tokens[0]}, median {tokens[len(tokens) // 2]}, max {tokens[-1]}",
            file=out,
        )
    print(f"  excluded pages (statements): {sorted(excluded)}", file=out)
    for section, n in sorted(by_section.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {section:30} {n}", file=out)


def dump_json(
    pdf: Path, sha256: str, chunks: list[Chunk], excluded: dict[int, str], out: TextIO
) -> None:
    print(json.dumps(as_json(pdf, sha256, chunks, excluded), ensure_ascii=False), file=out)
