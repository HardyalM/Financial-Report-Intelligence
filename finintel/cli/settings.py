"""Runtime settings from the environment, with an optional `.env` (never committed).

Real environment variables win over `.env`. Every vendor key is optional: without one, the
matching engine is skipped and recorded, and the local path keeps working.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from finintel.parse.engines.azure_di_engine import AzureDiConfig

LOG_FORMATS = ("console", "json")


@dataclass(frozen=True)
class Settings:
    artifacts_dir: Path
    cache_dir: Path
    azure: AzureDiConfig | None
    log_format: str
    log_level: str


def read_dotenv(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines. Supports `export`, quotes and trailing ` #` comments."""
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        values[key.strip()] = value
    return values


def load_settings(
    environ: Mapping[str, str] | None = None, dotenv_path: Path | None = Path(".env")
) -> Settings:
    live = os.environ if environ is None else environ
    env = {**(read_dotenv(dotenv_path) if dotenv_path else {}), **live}
    artifacts = Path(env.get("FININTEL_ARTIFACTS_DIR") or "artifacts")
    log_format = (env.get("FININTEL_LOG_FORMAT") or "console").lower()
    if log_format not in LOG_FORMATS:
        raise ValueError(f"FININTEL_LOG_FORMAT must be one of {LOG_FORMATS}, not {log_format!r}")
    return Settings(
        artifacts_dir=artifacts,
        cache_dir=Path(env.get("FININTEL_CACHE_DIR") or artifacts / "cache"),
        azure=AzureDiConfig.from_env(env),
        log_format=log_format,
        log_level=(env.get("FININTEL_LOG_LEVEL") or "WARNING").upper(),
    )
