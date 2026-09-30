"""Azure DI raw call: submit, poll, succeed or fail loudly; the key never leaks.

Every test drives the real client code against httpx.MockTransport. No socket is opened.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
import pytest

from finintel.parse.engines.azure_di_engine import (
    DEFAULT_API_VERSION,
    AzureDiConfig,
    AzureDiEngine,
    AzureDiError,
    page_ranges,
)

KEY = "sk-test-SECRET-4f1c"
ENDPOINT = "https://example-di.cognitiveservices.azure.com"
OPERATION = f"{ENDPOINT}/documentintelligence/documentModels/prebuilt-layout/analyzeResults/op-1"
SUCCEEDED = {
    "status": "succeeded",
    "analyzeResult": {"apiVersion": DEFAULT_API_VERSION, "pages": [{"pageNumber": 1}]},
}


@dataclass
class FakeVendor:
    """Scripted Azure: a submit response, then poll responses in order."""

    submit: httpx.Response
    polls: list[httpx.Response] = field(default_factory=list)
    requests: list[httpx.Request] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "POST":
            return self.submit
        return self.polls.pop(0) if len(self.polls) > 1 else self.polls[0]


def _accepted(retry_after: str = "1") -> httpx.Response:
    return httpx.Response(
        202, headers={"Operation-Location": OPERATION, "Retry-After": retry_after}
    )


def _engine(
    vendor: FakeVendor, *, clock: Callable[[], float] | None = None, timeout: float = 300.0
) -> tuple[AzureDiEngine, list[float]]:
    slept: list[float] = []
    config = AzureDiConfig(endpoint=ENDPOINT, key=KEY, poll_timeout_s=timeout)
    client = httpx.Client(transport=httpx.MockTransport(vendor.handler))
    engine = AzureDiEngine(config, client=client, sleep=slept.append, clock=clock or (lambda: 0.0))
    return engine, slept


def test_page_ranges() -> None:
    assert page_ranges([1, 2, 3, 7]) == "1-3,7"
    assert page_ranges([9, 5, 5, 6]) == "5-6,9"
    assert page_ranges([4]) == "4"
    for bad in ([], [0, 1]):
        with pytest.raises(ValueError):
            page_ranges(bad)


def test_config_from_env() -> None:
    assert AzureDiConfig.from_env({}) is None
    assert AzureDiConfig.from_env({"AZURE_DI_ENDPOINT": ENDPOINT}) is None
    assert AzureDiConfig.from_env({"AZURE_DI_KEY": KEY, "AZURE_DI_ENDPOINT": "  "}) is None
    config = AzureDiConfig.from_env(
        {"AZURE_DI_ENDPOINT": ENDPOINT + "/", "AZURE_DI_KEY": KEY, "FININTEL_AZURE_DI_MODEL": ""}
    )
    assert config is not None
    assert config.endpoint == ENDPOINT and config.model_id == "prebuilt-layout"
    assert config.api_version == DEFAULT_API_VERSION
    assert KEY not in repr(config)


def test_cache_config_excludes_secrets_and_endpoint() -> None:
    config = AzureDiConfig(endpoint=ENDPOINT, key=KEY)
    cache_config = config.cache_config("1-3")
    assert cache_config == {
        "api_version": DEFAULT_API_VERSION,
        "model_id": "prebuilt-layout",
        "pages": "1-3",
    }
    assert config.cache_config(None)["pages"] == "all"


def test_submit_poll_succeed() -> None:
    running = httpx.Response(200, json={"status": "running"}, headers={"Retry-After": "30"})
    vendor = FakeVendor(_accepted("0"), [running, httpx.Response(200, json=SUCCEEDED)])
    engine, slept = _engine(vendor)
    body = engine.analyze_raw(b"%PDF-1.7 bytes", pages="140-150")
    assert body == SUCCEEDED

    submit, *polls = vendor.requests
    assert submit.method == "POST"
    assert submit.url.path == "/documentintelligence/documentModels/prebuilt-layout:analyze"
    assert submit.url.params["api-version"] == DEFAULT_API_VERSION
    assert submit.url.params["pages"] == "140-150"
    assert submit.headers["Ocp-Apim-Subscription-Key"] == KEY
    assert submit.headers["Content-Type"] == "application/pdf"
    assert submit.content == b"%PDF-1.7 bytes"
    assert [str(p.url) for p in polls] == [OPERATION, OPERATION]
    assert all(p.headers["Ocp-Apim-Subscription-Key"] == KEY for p in polls)
    assert slept == [1.0, 10.0]  # Retry-After bounded to 1-10 s


def test_whole_document_sends_no_pages_parameter() -> None:
    vendor = FakeVendor(_accepted(), [httpx.Response(200, json=SUCCEEDED)])
    engine, _ = _engine(vendor)
    engine.analyze_raw(b"%PDF")
    assert "pages" not in vendor.requests[0].url.params


def test_rejected_submit_is_an_error_without_the_key() -> None:
    denied = httpx.Response(
        401, json={"error": {"code": "401", "message": "Access denied due to invalid key"}}
    )
    engine, _ = _engine(FakeVendor(denied))
    with pytest.raises(AzureDiError) as caught:
        engine.analyze_raw(b"%PDF")
    assert caught.value.code == "http_error" and caught.value.status_code == 401
    assert "invalid key" in str(caught.value) and KEY not in str(caught.value)


def test_failed_operation_is_an_error() -> None:
    failed = {"status": "failed", "error": {"code": "InvalidContent", "message": "corrupt"}}
    engine, _ = _engine(FakeVendor(_accepted(), [httpx.Response(200, json=failed)]))
    with pytest.raises(AzureDiError, match="InvalidContent") as caught:
        engine.analyze_raw(b"%PDF")
    assert caught.value.code == "operation_failed"


def test_poll_times_out() -> None:
    running = httpx.Response(200, json={"status": "running"})
    ticks = iter(range(0, 10_000, 100))
    engine, slept = _engine(
        FakeVendor(_accepted(), [running]), clock=lambda: float(next(ticks)), timeout=300
    )
    with pytest.raises(AzureDiError) as caught:
        engine.analyze_raw(b"%PDF")
    assert caught.value.code == "timeout"
    assert len(slept) == 3


def test_accepted_without_operation_location_is_bad_response() -> None:
    engine, _ = _engine(FakeVendor(httpx.Response(202)))
    with pytest.raises(AzureDiError) as caught:
        engine.analyze_raw(b"%PDF")
    assert caught.value.code == "bad_response"


def test_poll_http_error() -> None:
    engine, _ = _engine(FakeVendor(_accepted(), [httpx.Response(500, text="oops")]))
    with pytest.raises(AzureDiError) as caught:
        engine.analyze_raw(b"%PDF")
    assert caught.value.code == "http_error" and caught.value.status_code == 500


def test_transport_failure_is_wrapped() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    config = AzureDiConfig(endpoint=ENDPOINT, key=KEY)
    engine = AzureDiEngine(config, client=httpx.Client(transport=httpx.MockTransport(refuse)))
    with pytest.raises(AzureDiError) as caught:
        engine.analyze_raw(b"%PDF")
    assert caught.value.code == "transport_error"


def test_poll_body_that_is_not_json_is_bad_response() -> None:
    engine, _ = _engine(FakeVendor(_accepted(), [httpx.Response(200, text="<html>proxy</html>")]))
    with pytest.raises(AzureDiError) as caught:
        engine.analyze_raw(b"%PDF")
    assert caught.value.code == "bad_response"


def test_unexpected_failure_is_wrapped_without_its_message() -> None:
    def leaky(request: httpx.Request) -> httpx.Response:
        raise RuntimeError(f"proxy said no; headers were {dict(request.headers)}")

    config = AzureDiConfig(endpoint=ENDPOINT, key=KEY)
    engine = AzureDiEngine(config, client=httpx.Client(transport=httpx.MockTransport(leaky)))
    with pytest.raises(AzureDiError) as caught:
        engine.analyze_raw(b"%PDF")
    assert caught.value.code == "unexpected_error"
    assert str(caught.value) == "azure_di unexpected_error: RuntimeError"


def test_no_credentials() -> None:
    with pytest.raises(AzureDiError) as caught:
        AzureDiEngine(None).analyze_raw(b"%PDF")
    assert caught.value.code == "no_credentials"


def test_no_credentials_means_no_vendor_call() -> None:
    with pytest.raises(AzureDiError) as caught:
        AzureDiEngine().analyze_raw(b"%PDF")
    assert caught.value.code == "no_credentials"
