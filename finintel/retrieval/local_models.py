"""Local models: BAAI/bge-m3 dense embeddings (1024-d). Needs the optional `local` extra.

The `Embedder` interface is the seam: a Voyage adapter can replace this without touching the
pipeline. `MemoEmbedder` persists vectors per (model, text) so re-indexing a document the model has
already seen costs nothing and gives identical vectors.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from finintel.retrieval.embeddings import Embedder

BGE_M3 = "BAAI/bge-m3"
BGE_M3_DIM = 1024


class BgeM3Embedder:
    model_id = BGE_M3
    dim = BGE_M3_DIM

    def __init__(self, device: str | None = None, batch_size: int = 16) -> None:
        self._device = device
        self._batch = batch_size
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            device = self._device
            if device is None:
                import torch

                device = "mps" if torch.backends.mps.is_available() else "cpu"
            self._model = SentenceTransformer(BGE_M3, device=device)
            self._model.max_seq_length = 1024  # chunks are <= 600 tokens; keeps memory bounded
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vecs = self._load().encode(
            texts, batch_size=self._batch, normalize_embeddings=True, show_progress_bar=False
        )
        return [[float(x) for x in v] for v in vecs]


class MemoEmbedder:
    """Wrap an embedder with an on-disk cache keyed by sha256(text), one file per model."""

    def __init__(self, inner: Embedder, directory: Path) -> None:
        self._inner = inner
        self.model_id = inner.model_id
        self.dim = inner.dim
        safe = inner.model_id.replace("/", "__")
        self._file = directory / f"embeddings_{safe}.json"
        self._store: dict[str, list[float]] = {}
        if self._file.is_file():
            self._store = json.loads(self._file.read_text(encoding="utf-8"))

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def embed(self, texts: list[str]) -> list[list[float]]:
        missing = sorted({t for t in texts if self._key(t) not in self._store})
        if missing:
            for t, v in zip(missing, self._inner.embed(missing), strict=True):
                self._store[self._key(t)] = v
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(json.dumps(self._store), encoding="utf-8")
        return [self._store[self._key(t)] for t in texts]
