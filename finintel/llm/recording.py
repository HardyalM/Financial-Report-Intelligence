"""Record and replay provider calls (M5.2 gate: a recorded run replays offline, byte for byte).

A recording maps sha256(system, user) to the model's reply. Replay needs no network and no key; a
prompt it has not recorded is an error, never a silent fallback.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from finintel.llm import LLMProvider


def call_key(system: str, user: str) -> str:
    return hashlib.sha256(f"{system}\x00{user}".encode()).hexdigest()


class ReplayMissError(KeyError):
    """The prompt was not in the recording (the prompt, evidence or packs changed)."""


class RecordingProvider:
    def __init__(self, inner: LLMProvider) -> None:
        self.inner = inner
        self.name = inner.name
        self.model_id: str = getattr(inner, "model_id", inner.name)
        self.calls: dict[str, str] = {}

    def complete(self, system: str, user: str) -> str:
        reply = self.inner.complete(system, user)
        self.calls[call_key(system, user)] = reply
        return reply

    def recording(self) -> dict[str, Any]:
        return {"provider": self.name, "model_id": self.model_id, "calls": dict(self.calls)}


class ReplayProvider:
    def __init__(self, recording: Mapping[str, Any]) -> None:
        self.name: str = recording["provider"]
        self.model_id: str = recording["model_id"]
        self._calls: Mapping[str, str] = recording["calls"]

    def complete(self, system: str, user: str) -> str:
        try:
            return self._calls[call_key(system, user)]
        except KeyError as exc:
            raise ReplayMissError("prompt not in the recording") from exc
