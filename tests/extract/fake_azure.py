"""A stand-in for Azure DI `prebuilt-layout`, shaped after its documented v4 response.

NOT a recorded vendor response: there is no Azure key yet, so a real response has never been
captured. This builds one table per page from the PDF's own text layer (phrases separated by more
than 8 pt become cells; geometry in inches, as the service returns for PDFs). It exercises
normalisation, anchoring and voting end to end. Verifying behaviour on real Azure output is the
open M2.5 gate item.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from finintel.locate.signals import PageView
from finintel.parse.engines.azure_di_engine import AzureDiConfig, AzureDiEngine
from finintel.parse.text_layer import TextLayer

GAP = 8.0
CONFIG = AzureDiConfig(endpoint="https://example-di.cognitiveservices.azure.com", key="test-key")


def layout_body(layer: TextLayer, pages: Sequence[int]) -> dict[str, Any]:
    tables, page_info = [], []
    for number in pages:
        page = layer.page(number)
        view = PageView(page)
        page_info.append(
            {
                "pageNumber": number,
                "width": page.width / 72,
                "height": page.height / 72,
                "unit": "inch",
            }
        )
        cells, max_cols = [], 0
        for r, row in enumerate(view.row_boxes):
            phrases: list[list[tuple[str, tuple[float, float, float, float]]]] = []
            for word, box in row:
                if phrases and box[0] - phrases[-1][-1][1][2] <= GAP:
                    phrases[-1].append((word.text, box))
                else:
                    phrases.append([(word.text, box)])
            for c, phrase in enumerate(phrases):
                x0, x1 = min(b[0] for _, b in phrase), max(b[2] for _, b in phrase)
                y0, y1 = min(b[1] for _, b in phrase), max(b[3] for _, b in phrase)
                poly = [x0, y0, x1, y0, x1, y1, x0, y1]
                cells.append(
                    {
                        "rowIndex": r,
                        "columnIndex": c,
                        "content": " ".join(w for w, _ in phrase),
                        "boundingRegions": [
                            {"pageNumber": number, "polygon": [v / 72 for v in poly]}
                        ],
                    }
                )
            max_cols = max(max_cols, len(phrases))
        tables.append({"rowCount": len(view.row_boxes), "columnCount": max_cols, "cells": cells})
    return {"status": "succeeded", "analyzeResult": {"pages": page_info, "tables": tables}}


def alter(body: dict[str, Any], old: str, new: str) -> dict[str, Any]:
    """A vendor that 'corrects' a figure: the first cell whose content is `old` now says `new`."""
    out: dict[str, Any] = json.loads(json.dumps(body))
    for table in out["analyzeResult"]["tables"]:
        for cell in table["cells"]:
            if cell["content"] == old:
                cell["content"] = new
                return out
    raise AssertionError(f"no cell {old!r}")


def engine_for(
    body: dict[str, Any] | Callable[[], dict[str, Any]] | int,
    calls: list[str] | None = None,
    urls: list[str] | None = None,
) -> AzureDiEngine:
    """A real AzureDiEngine over a mock transport; an int is an HTTP error status."""

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request.method)
        if urls is not None:
            urls.append(str(request.url))
        if isinstance(body, int):
            return httpx.Response(body, json={"error": {"code": str(body), "message": "denied"}})
        if request.method == "POST":
            return httpx.Response(202, headers={"Operation-Location": "https://op/1"})
        return httpx.Response(200, json=body() if callable(body) else body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return AzureDiEngine(CONFIG, client=client, sleep=lambda _: None)
