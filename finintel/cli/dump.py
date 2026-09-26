"""Write an inspection dump directory atomically.

The dump is assembled in a staging directory next to the target and swapped in at the end, so a
reader never sees a half-written dump, and files from an earlier run (for example thumbnails of
pages that no longer rank) never survive a re-run.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from finintel.parse.engines.pdfplumber_engine import RawPageTables


def page_file(page: int, suffix: str) -> str:
    return f"p{page:04d}.{suffix}"


def write_dump(
    dump_dir: Path,
    *,
    summary: Mapping[str, Any],
    pages: Sequence[Mapping[str, Any]],
    outline: Sequence[Mapping[str, Any]],
    texts: Mapping[int, str],
    tables: Sequence[RawPageTables],
    thumbs: Mapping[int, bytes],
    azure_raw: Path | None,
) -> None:
    dump_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{dump_dir.name}.", dir=dump_dir.parent))
    try:
        _json(staging / "summary.json", summary)
        _json(staging / "outline.json", list(outline))
        (staging / "pages.jsonl").write_text(
            "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in pages),
            encoding="utf-8",
        )
        (staging / "text").mkdir()
        for page, text in texts.items():
            (staging / "text" / page_file(page, "txt")).write_text(text + "\n", encoding="utf-8")
        (staging / "tables").mkdir()
        for result in tables:
            _json(
                staging / "tables" / page_file(result.page, "json"), result.model_dump(mode="json")
            )
            (staging / "tables" / page_file(result.page, "txt")).write_text(
                render_tables(result), encoding="utf-8"
            )
        (staging / "thumbs").mkdir()
        for page, png in thumbs.items():
            (staging / "thumbs" / page_file(page, "png")).write_bytes(png)
        if azure_raw is not None:
            (staging / "azure").mkdir()
            _link_or_copy(azure_raw, staging / "azure" / "raw.json")
        _swap(staging, dump_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def render_tables(result: RawPageTables) -> str:
    """Tables as pipe-separated rows for reading. `∅` marks a cell pdfplumber returned as
    None; rows with no printed text are omitted here (the .json keeps every row)."""
    header = f"# pdfplumber raw tables · PDF page {result.page}"
    if result.error:
        return f"{header}\n# {result.error}\n"
    if not result.tables:
        return f"{header}\n# no tables found\n"
    blocks = [header]
    for index, table in enumerate(result.tables, start=1):
        box = ", ".join(f"{v:.1f}" for v in table.bbox)
        rows = [
            " | ".join("∅" if c is None else " ".join(c.split()) for c in r)
            for r in table.rows
            if any(c and c.strip() for c in r)
        ]
        omitted = len(table.rows) - len(rows)
        note = f" · {omitted} empty rows omitted (kept in .json)" if omitted else ""
        blocks.append(f"\n## table {index} · strategy {table.strategy} · bbox ({box}){note}")
        blocks.extend(rows)
    return "\n".join(blocks) + "\n"


def _json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _link_or_copy(source: Path, target: Path) -> None:
    """Hard-link large cached vendor responses into the dump; copy across filesystems."""
    try:
        os.link(source, target)
    except OSError:
        shutil.copyfile(source, target)


def _swap(staging: Path, dump_dir: Path) -> None:
    if dump_dir.exists():
        retired = Path(tempfile.mkdtemp(prefix=f".{dump_dir.name}.old.", dir=dump_dir.parent))
        os.replace(dump_dir, retired / dump_dir.name)
        os.replace(staging, dump_dir)
        shutil.rmtree(retired, ignore_errors=True)
    else:
        os.replace(staging, dump_dir)
