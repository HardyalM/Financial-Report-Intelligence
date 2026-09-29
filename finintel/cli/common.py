"""Helpers shared by `finintel` commands: the holdout guard, targets, and the cached text layer."""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

from finintel.cache import StageCache, StageKey
from finintel.parse.text_layer import EXTRACTOR, TEXT_LAYER_VERSION, TextLayer, read_text_layer

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


def text_layer_key(sha256: str) -> StageKey:
    return StageKey.build(sha256, "text_layer", TEXT_LAYER_VERSION, {"extractor": EXTRACTOR})


def cached_text_layer(pdf: Path, sha256: str, cache: StageCache) -> tuple[TextLayer, bool]:
    """(text layer, cache hit). Computed once per document and text-layer version."""
    data, hit = cache.memo(
        text_layer_key(sha256), "text_layer.json", lambda: read_text_layer(pdf).to_json()
    )
    return TextLayer.from_json(data), hit
