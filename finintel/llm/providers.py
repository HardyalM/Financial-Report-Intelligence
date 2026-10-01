"""Which provider runs the commentary. The label of the one actually used goes on every run.

Default is local Ollama. FININTEL_PROVIDER=gemini|anthropic selects a hosted provider, and only if
its key is set; FININTEL_PROVIDER=none (or extractive) selects no model at all. A key being present
never switches the provider by itself.
"""

from __future__ import annotations

from collections.abc import Mapping

from finintel.llm import LLMProvider
from finintel.llm.anthropic_provider import provider_from_env as anthropic_from_env
from finintel.llm.openai_compat import gemini, local_ollama

CHOICES = ("local", "gemini", "anthropic", "none", "extractive")


def select_provider(env: Mapping[str, str]) -> LLMProvider | None:
    choice = (env.get("FININTEL_PROVIDER", "").strip() or "local").lower()
    if choice not in CHOICES:
        raise ValueError(f"FININTEL_PROVIDER must be one of {CHOICES}, not {choice!r}")
    if choice in ("none", "extractive"):
        return None
    if choice == "gemini":
        return gemini(env)
    if choice == "anthropic":
        return anthropic_from_env(env)
    return local_ollama(env)
