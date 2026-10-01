"""OpenAI-compatible chat adapter: local Ollama (default) and Gemini's compatible endpoint.

`name` is the provider label recorded on every run: "local" or "gemini". Output is requested as a
JSON object; the validators, not the model, decide what is shown. Keys never appear in logs, errors
or artefacts. Not exercised against a live endpoint in CI (no network in unit tests).
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

import httpx
import structlog

from finintel.llm.anthropic_provider import LLMError

log = structlog.get_logger(__name__)

OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "llama3.1"
#: Ollama serves the OpenAI-compatible endpoint with a fixed 4,096-token context (measured: a longer
#: prompt loses its first lines, which are the rules). Prompts are sized to fit, and refused if not.
ATTEMPTS = 2
BACKOFF_S = 8.0
LOCAL_TIMEOUT_S = 180.0
LOCAL_MAX_TOKENS = 800
LOCAL_EVIDENCE_TOKENS = 900
LOCAL_MAX_PROMPT_CHARS = 10_500
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
GEMINI_MAX_TOKENS = 4096  # room for a model that spends tokens thinking before it answers
GEMINI_MODEL = (
    "gemini-3.1-flash-lite"  # the 3.x flash models returned 503 under load; override: GEMINI_MODEL
)


class OpenAICompatProvider:
    def __init__(
        self,
        name: str,
        *,
        base_url: str,
        path: str,
        model_id: str,
        api_key: str,
        max_tokens: int = 2048,
        context_tokens: int | None = None,
        max_prompt_chars: int | None = None,
        send_seed: bool = False,
        attempts: int = ATTEMPTS,
        timeout_s: float = 900.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.name = name
        self.model_id = model_id
        self._url = base_url.rstrip("/") + path
        self._key = api_key
        self._max_tokens = max_tokens
        self._max_prompt_chars = max_prompt_chars
        self._send_seed = send_seed  # Gemini's compatible endpoint rejects `seed`
        self._attempts = attempts
        if context_tokens is not None:
            self.context_tokens = context_tokens  # evidence tokens per call (small local contexts)
        self._timeout = timeout_s
        self._client = client

    def __repr__(self) -> str:
        return f"OpenAICompatProvider(name={self.name!r}, model_id={self.model_id!r})"

    def complete(self, system: str, user: str) -> str:
        if self._max_prompt_chars is not None and len(system) + len(user) > self._max_prompt_chars:
            # A prompt past the model's context is silently cut from the front (the rules go first).
            raise LLMError("prompt_too_long", f"{self.name}: {len(system) + len(user)} chars")
        last: LLMError | None = None
        for attempt in range(self._attempts):  # a stuck generation or a 5xx: one more try, new seed
            try:
                return self._once(system, user, seed=attempt)
            except LLMError as exc:
                if exc.code not in ("transport_error", "http_error") or (
                    exc.code == "http_error" and "HTTP 5" not in str(exc)
                ):
                    raise
                last = exc
                log.warning("llm.retry", provider=self.name, attempt=attempt + 1, code=exc.code)
                time.sleep(BACKOFF_S * (attempt + 1))
        assert last is not None
        raise last

    def _once(self, system: str, user: str, *, seed: int) -> str:
        client = self._client or httpx.Client(timeout=self._timeout)
        try:
            response = client.post(
                self._url,
                headers={"authorization": f"Bearer {self._key}"},
                json={
                    "model": self.model_id,
                    "temperature": 0,
                    **({"seed": seed} if self._send_seed else {}),
                    "max_tokens": self._max_tokens,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
        except httpx.HTTPError as exc:
            raise LLMError("transport_error", f"{self.name}: {type(exc).__name__}") from exc
        finally:
            if self._client is None:
                client.close()
        if response.status_code != 200:
            raise LLMError("http_error", f"{self.name}: HTTP {response.status_code}")
        try:
            body: Mapping[str, Any] = response.json()
            text = str(body["choices"][0]["message"]["content"] or "")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("bad_response", f"{self.name}: {type(exc).__name__}") from exc
        log.info("llm.complete", provider=self.name, model=self.model_id, prompt_chars=len(user))
        return text


def local_ollama(env: Mapping[str, str]) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        "local",
        base_url=env.get("OLLAMA_BASE_URL", "").strip() or OLLAMA_URL,
        path="/v1/chat/completions",
        model_id=env.get("OLLAMA_MODEL", "").strip() or OLLAMA_MODEL,
        api_key="ollama",  # Ollama ignores it; the client wants one
        max_tokens=LOCAL_MAX_TOKENS,
        send_seed=True,
        timeout_s=LOCAL_TIMEOUT_S,
        context_tokens=LOCAL_EVIDENCE_TOKENS,
        max_prompt_chars=LOCAL_MAX_PROMPT_CHARS,
    )


def gemini(env: Mapping[str, str]) -> OpenAICompatProvider | None:
    key = env.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    return OpenAICompatProvider(
        "gemini",
        base_url=GEMINI_URL,
        path="/chat/completions",
        model_id=env.get("GEMINI_MODEL", "").strip() or GEMINI_MODEL,
        api_key=key,
        max_tokens=GEMINI_MAX_TOKENS,
        attempts=4,
    )
