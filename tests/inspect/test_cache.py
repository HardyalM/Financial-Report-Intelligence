"""Content-addressed stage cache: stable keys, atomic entries, honest hits."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from finintel.cache import MANIFEST, StageCache, StageKey, config_hash

SHA = "ab" * 32


def _key(**config: object) -> StageKey:
    return StageKey.build(SHA, "text_layer", "1", config)


def test_config_hash_ignores_key_order_and_tracks_values() -> None:
    assert config_hash({"a": 1, "b": [1, 2]}) == config_hash({"b": [1, 2], "a": 1})
    assert config_hash({"a": 1}) != config_hash({"a": 2})
    assert len(config_hash({})) == 16


@pytest.mark.parametrize(
    ("sha", "stage", "version"),
    [("nothex", "text_layer", "1"), (SHA, "../escape", "1"), (SHA, "text_layer", "1/2")],
)
def test_key_rejects_unsafe_values(sha: str, stage: str, version: str) -> None:
    with pytest.raises(ValueError):
        StageKey.build(sha, stage, version, {})


def test_round_trip_and_manifest(tmp_path: Path) -> None:
    cache = StageCache(tmp_path)
    key = _key(engine="pymupdf 1.28.2")
    assert not cache.has(key) and cache.get(key, "a.json") is None
    path = cache.put(key, {"a.json": b"{}", "nested/b.bin": b"\x00\x01"})
    assert path == tmp_path / SHA / "text_layer" / "1" / key.config_hash
    assert cache.has(key)
    assert cache.get(key, "a.json") == b"{}" and cache.get(key, "nested/b.bin") == b"\x00\x01"
    assert cache.get(key, "absent") is None
    manifest = json.loads((path / MANIFEST).read_text())
    assert manifest["files"] == ["a.json", "nested/b.bin"] and manifest["sha256"] == SHA


def test_memo_computes_once(tmp_path: Path) -> None:
    cache, calls = StageCache(tmp_path), []

    def compute() -> bytes:
        calls.append(1)
        return b"payload"

    assert cache.memo(_key(), "x", compute) == (b"payload", False)
    assert cache.memo(_key(), "x", compute) == (b"payload", True)
    assert len(calls) == 1


def test_different_config_is_a_different_entry(tmp_path: Path) -> None:
    cache = StageCache(tmp_path)
    cache.put(_key(page=1), {"x": b"1"})
    assert cache.get(_key(page=2), "x") is None


def test_failed_compute_leaves_no_entry(tmp_path: Path) -> None:
    cache = StageCache(tmp_path)

    def boom() -> bytes:
        raise RuntimeError("engine crashed")

    with pytest.raises(RuntimeError):
        cache.memo(_key(), "x", boom)
    assert not cache.has(_key())


def test_interrupted_write_leaves_no_entry_and_no_debris(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = StageCache(tmp_path)
    real = Path.write_bytes

    def fail_second(self: Path, data: bytes) -> int:
        if self.name == "second":
            raise OSError("disk full")
        return real(self, data)

    monkeypatch.setattr(Path, "write_bytes", fail_second)
    with pytest.raises(OSError):
        cache.put(_key(), {"first": b"1", "second": b"2"})
    assert not cache.has(_key())
    assert list(cache.path(_key()).parent.iterdir()) == []


def test_directory_without_manifest_is_a_miss(tmp_path: Path) -> None:
    cache = StageCache(tmp_path)
    partial = cache.path(_key())
    partial.mkdir(parents=True)
    (partial / "x").write_bytes(b"half")
    assert not cache.has(_key()) and cache.get(_key(), "x") is None


def test_put_replaces_an_entry_completely(tmp_path: Path) -> None:
    cache = StageCache(tmp_path)
    cache.put(_key(), {"old": b"1"})
    cache.put(_key(), {"new": b"2"})
    assert cache.get(_key(), "old") is None and cache.get(_key(), "new") == b"2"


def test_manifest_name_is_reserved(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        StageCache(tmp_path).put(_key(), {MANIFEST: b"{}"})
