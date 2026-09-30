"""Helpers shared by `finintel` commands: the holdout guard, targets, and the cached text layer."""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

from finintel.parse.cached import cached_text_layer, text_layer_key

FIXTURE_PDFS = Path("fixtures") / "pdfs"


class HoldoutRefusedError(Exception):
    """The path is inside fixtures/holdout/, which no tool may read before M8.3."""


def is_holdout(path: Path) -> bool:
    """True if the resolved path lies under a `fixtures/holdout` directory (symlinks followed)."""
    parts = [p.lower() for p in path.resolve().parts]
    return any(a == "fixtures" and b == "holdout" for a, b in pairwise(parts))


def resolve_pdf(target: str) -> Path:
    """A PDF path, or a fixture name such as "company_a" for fixtures/pdfs/company_a.pdf."""
    path = Path(target)
    if not path.exists() and path.suffix == "" and (FIXTURE_PDFS / f"{target}.pdf").exists():
        path = FIXTURE_PDFS / f"{target}.pdf"
    if is_holdout(path):
        raise HoldoutRefusedError(str(path))
    if not path.is_file():
        raise FileNotFoundError(f"{target}: no such PDF (or fixture name in {FIXTURE_PDFS}/)")
    return path


__all__ = [
    "FIXTURE_PDFS",
    "HoldoutRefusedError",
    "cached_text_layer",
    "is_holdout",
    "resolve_pdf",
    "text_layer_key",
]
