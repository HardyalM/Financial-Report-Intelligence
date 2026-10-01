"""Locked contracts (ADR-006).

`schemas/*.json` are canonical. The models in this package are generated from them by
`scripts/gen_contracts.py` and are typed views; `validate_pack` (JSON Schema) is the
validation authority, including the conditional v1.1.0 rules the models do not express.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from finintel.contracts.commentary import Citation, Commentary, Paragraph, Topic
from finintel.contracts.ratio_pack import RatioPack
from finintel.contracts.statement_pack import LineItem, PeriodValue, StatementPack

__all__ = [
    "CANONICAL_ITEMS",
    "Citation",
    "Commentary",
    "LineItem",
    "Paragraph",
    "PeriodValue",
    "RatioPack",
    "StatementPack",
    "Topic",
    "load_schema",
    "schema_dir",
    "validate_pack",
    "validate_ratio_pack",
]


def schema_dir() -> Path:
    """Directory holding the locked JSON Schemas (repo checkout or installed wheel)."""
    here = Path(__file__).resolve()
    for candidate in (here.parents[2] / "schemas", here.parents[1] / "_schemas"):
        if (candidate / "statement_pack.schema.json").is_file():
            return candidate
    raise FileNotFoundError("schemas/statement_pack.schema.json not found")


@cache
def load_schema(name: str = "statement_pack") -> dict[str, Any]:
    """Load a locked schema by stem, e.g. "statement_pack"."""
    path = schema_dir() / f"{name}.schema.json"
    schema: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def validate_pack(pack: dict[str, Any]) -> list[str]:
    """Validate a StatementPack against the JSON Schema. Returns messages; empty means valid."""
    validator = Draft202012Validator(load_schema("statement_pack"))
    errors = sorted(validator.iter_errors(pack), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors]


#: Canonical line-item ids named in the schema (documented in docs/SCHEMA.md section 5 and 9).
CANONICAL_ITEMS: tuple[str, ...] = tuple(load_schema()["properties"]["items"]["properties"])


def validate_ratio_pack(pack: dict[str, Any]) -> list[str]:
    """Validate a RatioPack against its JSON Schema. Returns messages; empty means valid."""
    validator = Draft202012Validator(load_schema("ratio_pack"))
    errors = sorted(validator.iter_errors(pack), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors]
