"""LLM provider adapters, record/replay cache and tracing. Model ids are configuration."""

from typing import Any, Protocol


class LLMProvider(Protocol):
    """Adapter interface. Structured output only; no output field is ever a number for a pack."""

    name: str

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Return a response validated against `schema`."""
        ...
