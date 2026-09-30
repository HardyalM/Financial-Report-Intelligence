"""The text layer, computed once per document and text-layer version (content-addressed cache)."""

from __future__ import annotations

from pathlib import Path

from finintel.cache import StageCache, StageKey
from finintel.parse.text_layer import EXTRACTOR, TEXT_LAYER_VERSION, TextLayer, read_text_layer


def text_layer_key(sha256: str) -> StageKey:
    return StageKey.build(sha256, "text_layer", TEXT_LAYER_VERSION, {"extractor": EXTRACTOR})


def cached_text_layer(pdf: Path, sha256: str, cache: StageCache) -> tuple[TextLayer, bool]:
    """(text layer, cache hit)."""
    data, hit = cache.memo(
        text_layer_key(sha256), "text_layer.json", lambda: read_text_layer(pdf).to_json()
    )
    return TextLayer.from_json(data), hit
