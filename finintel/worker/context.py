"""What a worker needs to run stages: storage, caches, engines and the model seams."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from finintel.llm import LLMProvider
from finintel.parse.engines.azure_di_engine import AzureDiEngine
from finintel.retrieval.embeddings import Embedder
from finintel.storage import FilesystemStore


class InjectedCrash(BaseException):
    """A test-injected worker death. Not an Exception, so no handler records it as a failure."""


@dataclass
class Hooks:
    """Observation and fault-injection points. All optional; the default does nothing."""

    on_execute: Callable[[str], None] | None = None  # a stage function is about to run
    during_stage: Callable[[str], None] | None = None  # inside the stage transaction, before commit
    after_stage: Callable[[str], None] | None = None  # after the stage committed as done


@dataclass
class RunContext:
    store: FilesystemStore
    cache_dir: Path
    embedder: Embedder
    provider: LLMProvider | None = None  # None: extractive commentary
    azure: AzureDiEngine | None = None
    engines: str = "local"  # "all" adds the Azure DI family when `azure` is configured
    max_attempts: int = 3
    backoff_s: float = 2.0
    lease_s: float = 900.0  # a `running` job older than this is a dead worker's
    hooks: Hooks = field(default_factory=Hooks)
