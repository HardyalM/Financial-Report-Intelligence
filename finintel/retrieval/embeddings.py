"""Embedding providers. `FakeEmbedder` is deterministic and offline (unit tests, CI).

Voyage and local bge-m3 adapters are not built yet: they need a key and a model download, and
the E3 report must record which model was used, so they land with the Postgres index.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

_TOKEN = re.compile(r"[a-z0-9']+")


class Embedder(Protocol):
    model_id: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class FakeEmbedder:
    """Hashed bag-of-words, L2-normalised. Similar wording gives high cosine; nothing semantic."""

    model_id = "fake-hash-bow-v1"

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in tokens(text):
            h = int.from_bytes(hashlib.sha256(tok.encode()).digest()[:4], "big")
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else vec


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))
