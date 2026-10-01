"""Provider selection and the OpenAI-compatible adapter (local Ollama, Gemini). No network."""

from __future__ import annotations

import json

import httpx
import pytest

from finintel.llm.anthropic_provider import LLMError
from finintel.llm.openai_compat import OpenAICompatProvider, gemini, local_ollama
from finintel.llm.providers import select_provider


def test_local_ollama_is_the_default_and_is_labelled_local() -> None:
    p = select_provider({})
    assert p is not None and p.name == "local"
    assert getattr(p, "model_id", None) == "llama3.1"
    # a hosted key present does not switch the provider by itself
    still = select_provider({"GEMINI_API_KEY": "g", "ANTHROPIC_API_KEY": "a"})
    assert still is not None and still.name == "local"


def test_hosted_providers_need_an_explicit_choice_and_a_key() -> None:
    g = select_provider({"FININTEL_PROVIDER": "gemini", "GEMINI_API_KEY": "g"})
    assert g is not None and g.name == "gemini"
    assert select_provider({"FININTEL_PROVIDER": "gemini"}) is None
    a = select_provider({"FININTEL_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "a"})
    assert a is not None and a.name == "anthropic"
    assert select_provider({"FININTEL_PROVIDER": "none"}) is None
    assert select_provider({"FININTEL_PROVIDER": "extractive"}) is None
    with pytest.raises(ValueError):
        select_provider({"FININTEL_PROVIDER": "bogus"})


def test_the_adapter_posts_an_openai_chat_request_and_reads_the_content() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": 1}'}}]})

    p = OpenAICompatProvider(
        "local", base_url="http://127.0.0.1:11434/", path="/v1/chat/completions",
        model_id="llama3.1", api_key="ollama",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )  # fmt: skip
    assert p.complete("sys", "usr") == '{"ok": 1}'
    [req] = seen
    body = json.loads(req.content)
    assert str(req.url) == "http://127.0.0.1:11434/v1/chat/completions"
    assert req.headers["authorization"] == "Bearer ollama"
    assert body["model"] == "llama3.1" and body["temperature"] == 0
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]


def test_failures_become_llm_errors_without_the_key() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    def denied(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="bad key sk-SECRET")

    def junk(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    for handler, code in (
        (refuse, "transport_error"),
        (denied, "http_error"),
        (junk, "bad_response"),
    ):
        p = OpenAICompatProvider(
            "gemini", base_url="https://x.test", path="/c", model_id="m", api_key="sk-SECRET",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )  # fmt: skip
        with pytest.raises(LLMError) as caught:
            p.complete("s", "u")
        assert caught.value.code == code and "SECRET" not in str(caught.value)
        assert "SECRET" not in repr(p)


def test_env_overrides_for_the_local_model() -> None:
    p = local_ollama({"OLLAMA_MODEL": "qwen2.5", "OLLAMA_BASE_URL": "http://box:1234"})
    assert p.model_id == "qwen2.5" and "box:1234" in p._url
    assert gemini({}) is None


def test_seed_is_sent_to_local_only_and_gemini_retries_server_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import time

    import finintel.llm.openai_compat as oc

    monkeypatch.setattr(time, "sleep", lambda s: None)
    bodies: list[dict[str, object]] = []
    replies = iter([503, 503, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        status = next(replies)
        if status != 200:
            return httpx.Response(status, text="busy")
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    g = oc.OpenAICompatProvider(
        "gemini", base_url="https://x.test", path="/c", model_id="m", api_key="k",
        attempts=4, client=client,
    )  # fmt: skip
    assert g.complete("s", "u") == "{}" and len(bodies) == 3
    assert all("seed" not in b for b in bodies)
    loc = oc.OpenAICompatProvider(
        "local", base_url="https://x.test", path="/c", model_id="m", api_key="k",
        send_seed=True, client=client,
    )  # fmt: skip
    replies = iter([200])
    loc.complete("s", "u")
    assert bodies[-1]["seed"] == 0
    assert gemini({"GEMINI_API_KEY": "k"}).model_id == "gemini-3.5-flash-lite"  # type: ignore[union-attr]
