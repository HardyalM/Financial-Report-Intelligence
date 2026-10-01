"""The commentary artefact: output, snapshot, metrics and the recorded model calls.

`output_bytes` is the canonical serialisation of the validated commentary. Replaying the recording
offline must reproduce it byte for byte (M5.2 gate).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from finintel.commentary.run import CommentaryRun
from finintel.contracts.commentary import Commentary


def output_bytes(commentary: Commentary) -> bytes:
    text = json.dumps(
        commentary.model_dump(mode="json"), sort_keys=True, indent=2, ensure_ascii=False
    )
    return (text + "\n").encode("utf-8")


def write_artifact(
    path: Path, run: CommentaryRun, recording: dict[str, Any] | None, extra: dict[str, Any]
) -> Path:
    body = {
        "output": run.commentary.model_dump(mode="json"),
        "numbers_snapshot": run.snapshot,
        "pre_validation": run.metrics,
        "fallback_reason": run.fallback_reason,
        "recording": recording,
        **extra,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(body, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def read_recording(path: Path) -> dict[str, Any]:
    body = json.loads(path.read_text(encoding="utf-8"))
    recording = body.get("recording")
    if not recording:
        raise ValueError(f"{path} holds no recorded model calls (it was an extractive run)")
    assert isinstance(recording, dict)
    return recording
