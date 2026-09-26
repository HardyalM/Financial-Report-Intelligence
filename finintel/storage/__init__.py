"""Object storage adapters: local filesystem (v1), Supabase Storage / S3 (v1.1)."""

from typing import Protocol


class ObjectStore(Protocol):
    """Content-addressed store for originals and stage artefacts."""

    def put(self, key: str, data: bytes) -> None:
        """Store bytes under a key."""
        ...

    def get(self, key: str) -> bytes:
        """Return the bytes stored under a key."""
        ...
