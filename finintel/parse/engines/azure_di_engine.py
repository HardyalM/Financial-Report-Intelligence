"""AzureDiEngine: the `azure_di` table engine (image_layout family).

M1 scope: the raw call and storage only. `analyze_raw` submits the PDF to Azure AI Document
Intelligence `prebuilt-layout`, polls the long-running operation, and returns the final response
body untouched. Normalisation into `StatementTable` and reconciliation are M2.5.

Missing credentials are not an error: the caller records `parser_skipped: ["azure_di"]` and the
local text-layer family carries on (ARCHITECTURE section 5.2). The subscription key never appears
in logs, exceptions, cache keys or artefacts.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import structlog

from finintel._placeholders import not_yet
from finintel.parse.engines.base import EngineFamily, ParsedTables

#: Bump when the stored raw response or the request shape changes. Part of the cache key.
RAW_RESPONSE_VERSION = "1"
DEFAULT_API_VERSION = "2024-11-30"
DEFAULT_MODEL_ID = "prebuilt-layout"
#: COST_AND_OPS section 1: about $10 per 1,000 pages (September 2026). Estimate only.
USD_PER_PAGE = 0.010

log = structlog.get_logger(__name__)


class AzureDiError(Exception):
    """The vendor call failed. The message never contains the key."""

    def __init__(self, code: str, message: str, status_code: int | None = None) -> None:
        super().__init__(f"azure_di {code}: {message}")
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class AzureDiConfig:
    endpoint: str
    key: str = field(repr=False)
    api_version: str = DEFAULT_API_VERSION
    model_id: str = DEFAULT_MODEL_ID
    poll_timeout_s: float = 300.0
    request_timeout_s: float = 120.0

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> AzureDiConfig | None:
        """Config from AZURE_DI_* variables, or None when the endpoint or key is unset."""
        endpoint = env.get("AZURE_DI_ENDPOINT", "").strip()
        key = env.get("AZURE_DI_KEY", "").strip()
        if not endpoint or not key:
            return None
        return cls(
            endpoint=endpoint.rstrip("/"),
            key=key,
            api_version=env.get("FININTEL_AZURE_DI_API_VERSION", "").strip() or DEFAULT_API_VERSION,
            model_id=env.get("FININTEL_AZURE_DI_MODEL", "").strip() or DEFAULT_MODEL_ID,
        )

    def cache_config(self, pages: str | None) -> dict[str, str]:
        """What determines the response. Excludes the key and the resource endpoint."""
        return {"api_version": self.api_version, "model_id": self.model_id, "pages": pages or "all"}


def page_ranges(pages: Iterable[int]) -> str:
    """Format 1-based pages as Azure's `pages` parameter, e.g. [1, 2, 3, 7] -> "1-3,7"."""
    ordered = sorted(set(pages))
    if not ordered or ordered[0] < 1:
        raise ValueError("pages must be a non-empty set of 1-based page numbers")
    parts: list[str] = []
    start = prev = ordered[0]
    for page in [*ordered[1:], None]:
        if page is not None and page == prev + 1:
            prev = page
            continue
        parts.append(str(start) if start == prev else f"{start}-{prev}")
        if page is not None:
            start = prev = page
    return ",".join(parts)


class AzureDiEngine:
    name = "azure_di"
    family = EngineFamily.IMAGE_LAYOUT

    def __init__(
        self,
        config: AzureDiConfig | None = None,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self._client = client
        self._sleep = sleep
        self._clock = clock

    def analyze_raw(self, pdf_bytes: bytes, pages: str | None = None) -> dict[str, Any]:
        """Run `prebuilt-layout` and return the final operation body (status "succeeded").

        Every failure surfaces as `AzureDiError`, so the caller can degrade to the local engines
        instead of losing the run. Unexpected errors carry only their type name: exception text
        from lower layers can echo request headers, and the key is one of them.
        """
        if self.config is None:
            raise AzureDiError("no_credentials", "AZURE_DI_ENDPOINT and AZURE_DI_KEY are not set")
        cfg = self.config
        client = self._client or httpx.Client(timeout=cfg.request_timeout_s)
        try:
            return self._analyze(client, cfg, pdf_bytes, pages)
        except AzureDiError:
            raise
        except httpx.HTTPError as exc:
            raise AzureDiError("transport_error", type(exc).__name__) from exc
        except ValueError as exc:  # a body that is not JSON
            raise AzureDiError("bad_response", type(exc).__name__) from exc
        except Exception as exc:  # sandboxed or proxied network, SSL stack, ...
            raise AzureDiError("unexpected_error", type(exc).__name__) from exc
        finally:
            if self._client is None:
                client.close()

    def parse(self, pdf_path: Path, pages: list[int] | None = None) -> ParsedTables:
        not_yet("M2.5", "AzureDiEngine.parse (StatementTable normalisation)")

    def _analyze(
        self, client: httpx.Client, cfg: AzureDiConfig, pdf_bytes: bytes, pages: str | None
    ) -> dict[str, Any]:
        url = f"{cfg.endpoint}/documentintelligence/documentModels/{cfg.model_id}:analyze"
        params = {"api-version": cfg.api_version, **({"pages": pages} if pages else {})}
        headers = {"Ocp-Apim-Subscription-Key": cfg.key}
        host = urlsplit(cfg.endpoint).hostname
        log.info("azure_di.submit", host=host, model=cfg.model_id, pages=pages or "all")
        submitted = client.post(
            url,
            params=params,
            headers={**headers, "Content-Type": "application/pdf"},
            content=pdf_bytes,
        )
        if submitted.status_code != 202:
            raise AzureDiError(
                "http_error", _vendor_message(submitted), status_code=submitted.status_code
            )
        operation = submitted.headers.get("operation-location")
        if not operation:
            raise AzureDiError("bad_response", "202 without an Operation-Location header")

        deadline = self._clock() + cfg.poll_timeout_s
        last = submitted
        while True:
            self._sleep(_retry_after(last))
            last = client.get(operation, headers=headers)
            if last.status_code != 200:
                raise AzureDiError(
                    "http_error", _vendor_message(last), status_code=last.status_code
                )
            body: dict[str, Any] = last.json()
            status = body.get("status")
            if status == "succeeded":
                pages_done = len((body.get("analyzeResult") or {}).get("pages") or ())
                log.info("azure_di.succeeded", host=host, pages=pages_done)
                return body
            if status in ("failed", "canceled"):
                raise AzureDiError("operation_failed", f"{status}: {_error_text(body)}")
            if self._clock() >= deadline:
                raise AzureDiError("timeout", f"still {status!r} after {cfg.poll_timeout_s:.0f}s")


def _retry_after(response: httpx.Response) -> float:
    """Seconds to wait before the next poll: the vendor's Retry-After, bounded to 1-10 s."""
    raw = response.headers.get("retry-after")
    try:
        seconds = float(raw) if raw is not None else 2.0
    except ValueError:
        seconds = 2.0
    return min(max(seconds, 1.0), 10.0)


def _error_text(body: Mapping[str, Any]) -> str:
    error = body.get("error") or {}
    return f"{error.get('code', '')} {str(error.get('message', ''))[:300]}".strip()


def _vendor_message(response: httpx.Response) -> str:
    """HTTP status plus the vendor's error code and message, when the body carries them."""
    try:
        body = response.json()
    except ValueError:
        body = {}
    detail = _error_text(body) if isinstance(body, dict) else ""
    return f"HTTP {response.status_code} {detail}".strip()
