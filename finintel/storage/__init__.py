"""Object storage adapters: local filesystem (v1), Supabase Storage / S3 (v1.1)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol


class ObjectStore(Protocol):
    """Content-addressed store for originals and stage artefacts."""

    def put(self, key: str, data: bytes) -> None:
        """Store bytes under a key."""
        ...

    def get(self, key: str) -> bytes:
        """Return the bytes stored under a key."""
        ...


class FilesystemStore:
    """Keys are relative paths under `root` (for example `sha256/<hash>.pdf`). Writes are atomic."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, key: str) -> Path:
        target = (self.root / key).resolve()
        if self.root.resolve() not in target.parents:
            raise ValueError(f"key escapes the store: {key!r}")
        return target

    def put(self, key: str, data: bytes) -> None:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + f".tmp{os.getpid()}")
        tmp.write_bytes(data)
        tmp.replace(target)

    def get(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self.path(key).is_file()
