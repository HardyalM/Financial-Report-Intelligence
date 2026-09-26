"""Content-addressed stage cache keyed by (sha256, stage, stage_version, config_hash).

Re-runs are free and deterministic, and a premium parse is paid for once per document per engine
version (ARCHITECTURE section 2). Layout:

    {root}/{sha256}/{stage}/{stage_version}/{config_hash}/
        _manifest.json      key fields and file list; written last
        <files>

An entry is written in full to a temporary sibling directory and renamed into place, so an entry
either exists completely or not at all. Secrets must never be part of a stage config.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MANIFEST = "_manifest.json"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SEGMENT = re.compile(r"^[A-Za-z0-9_.-]+$")


def config_hash(config: Mapping[str, Any]) -> str:
    """Stable hash of a JSON-serialisable stage config (key order does not matter)."""
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class StageKey:
    sha256: str
    stage: str
    stage_version: str
    config_hash: str

    def __post_init__(self) -> None:
        if not _SHA256.match(self.sha256):
            raise ValueError(f"not a SHA-256 hex digest: {self.sha256!r}")
        for name in ("stage", "stage_version", "config_hash"):
            if not _SEGMENT.match(getattr(self, name)):
                raise ValueError(f"unsafe cache path segment {name}={getattr(self, name)!r}")

    @classmethod
    def build(
        cls, sha256: str, stage: str, stage_version: str, config: Mapping[str, Any]
    ) -> StageKey:
        return cls(sha256, stage, stage_version, config_hash(config))

    @property
    def relpath(self) -> Path:
        return Path(self.sha256, self.stage, self.stage_version, self.config_hash)


class StageCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, key: StageKey) -> Path:
        return self.root / key.relpath

    def has(self, key: StageKey) -> bool:
        return (self.path(key) / MANIFEST).is_file()

    def get(self, key: StageKey, name: str) -> bytes | None:
        """Bytes of one file in a complete entry, or None on a miss."""
        if not self.has(key):
            return None
        target = self.path(key) / name
        return target.read_bytes() if target.is_file() else None

    def put(self, key: StageKey, files: Mapping[str, bytes]) -> Path:
        """Write a complete entry atomically. An existing entry for the key is replaced."""
        if MANIFEST in files:
            raise ValueError(f"{MANIFEST} is reserved")
        final = self.path(key)
        final.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{key.config_hash}.", dir=final.parent))
        try:
            for name, data in files.items():
                target = staging / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            manifest = {
                "sha256": key.sha256,
                "stage": key.stage,
                "stage_version": key.stage_version,
                "config_hash": key.config_hash,
                "files": sorted(files),
            }
            (staging / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            if final.exists():
                shutil.rmtree(final)
            os.replace(staging, final)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return final

    def memo(self, key: StageKey, name: str, compute: Callable[[], bytes]) -> tuple[bytes, bool]:
        """Return (bytes, hit). On a miss, compute, store as a one-file entry, and return."""
        cached = self.get(key, name)
        if cached is not None:
            return cached, True
        data = compute()
        self.put(key, {name: data})
        return data, False
