"""Anthropic Messages API adapter over httpx. The key never appears in logs, errors or artefacts.

Not exercised live in CI (no network in unit tests): tests drive it through httpx.MockTransport.
Without ANTHROPIC_API_KEY `provider_from_env` returns None and the caller runs extractive mode.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_BASE_URL = "https://api.anthropic.com"
API_VERSION = "2023-06-01"


class LLMError(Exception):
    """The vendor call failed. The message never contains the key."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(f"anthropic {code}: {message}".rstrip(": "))
        self.code = code


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        *,
        model_id: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        max_tokens: int = 2048,
        timeout_s: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._key = api_key
        self.model_id = model_id
        self._base = base_url.rstrip("/")
        self._max_tokens = max_tokens
        self._timeout = timeout_s
        self._client = client

    def __repr__(self) -> str:
        return f"AnthropicProvider(model_id={self.model_id!r})"

    def complete(self, system: str, user: str) -> str:
        client = self._client or httpx.Client(timeout=self._timeout)
        try:
            response = client.post(
                f"{self._base}/v1/messages",
                headers={
                    "x-api-key": self._key,
                    "anthropic-version": API_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": self.model_id,
                    "max_tokens": self._max_tokens,
                    "temperature": 0,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
        except httpx.HTTPError as exc:
            raise LLMError("transport_error", type(exc).__name__) from exc
        finally:
            if self._client is None:
                client.close()
        if response.status_code != 200:
            raise LLMError("http_error", f"HTTP {response.status_code} {_error_text(response)}")
        try:
            body: Mapping[str, Any] = response.json()
            blocks = body["content"]
            text = "".join(b["text"] for b in blocks if b.get("type") == "text")
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMError("bad_response", type(exc).__name__) from exc
        log.info("anthropic.complete", model=self.model_id, prompt_chars=len(user))
        return text


def _error_text(response: httpx.Response) -> str:
    try:
        error = response.json().get("error") or {}
        return f"{error.get('type', '')} {str(error.get('message', ''))[:200]}".strip()
    except (ValueError, AttributeError):
        return ""


def provider_from_env(env: Mapping[str, str]) -> AnthropicProvider | None:
    key = env.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return None
    return AnthropicProvider(
        key,
        model_id=env.get("FININTEL_COMMENTARY_MODEL", "").strip() or DEFAULT_MODEL,
        base_url=env.get("ANTHROPIC_BASE_URL", "").strip() or DEFAULT_BASE_URL,
    )
