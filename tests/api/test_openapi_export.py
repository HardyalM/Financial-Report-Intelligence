"""The committed OpenAPI document matches the app (runs in the default suite; no database)."""

from __future__ import annotations

import json
from pathlib import Path

from finintel.api import create_app

ROOT = Path(__file__).resolve().parents[2]


def test_schemas_openapi_json_is_current() -> None:
    committed = json.loads((ROOT / "schemas" / "openapi.json").read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(create_app().openapi(), sort_keys=True))
    assert {"/uploads", "/readyz", "/healthz"} <= set(committed["paths"])
