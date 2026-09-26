"""M0 smoke tests: the locked schema loads, the example pack validates, v1.1.0 rules hold."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from finintel.contracts import CANONICAL_ITEMS, StatementPack, load_schema, validate_pack

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "fixtures" / "expected" / "EXAMPLE_company_a.json"
LOCKED_RATIO_INPUTS = (
    "revenue",
    "operating_profit",
    "current_assets",
    "current_liabilities",
    "total_assets",
    "total_equity",
    "total_debt",
)


@pytest.fixture
def example() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    return data


def as_v110(pack: dict[str, Any]) -> dict[str, Any]:
    upgraded = copy.deepcopy(pack)
    upgraded["schema_version"] = "1.1.0"
    return upgraded


def test_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(load_schema())


def test_example_pack_validates(example: dict[str, Any]) -> None:
    assert validate_pack(example) == []


def test_example_pack_parses_into_contract(example: dict[str, Any]) -> None:
    pack = StatementPack.model_validate(example)
    assert pack.unit_scale == 1_000_000
    assert pack.items["revenue"].values[0].raw_text == "12,345"


def test_locked_ratio_inputs_are_canonical_items() -> None:
    assert set(LOCKED_RATIO_INPUTS) <= set(CANONICAL_ITEMS)


def test_example_is_also_valid_as_v110(example: dict[str, Any]) -> None:
    assert validate_pack(as_v110(example)) == []


def test_v100_pack_without_page_stays_valid(example: dict[str, Any]) -> None:
    del example["items"]["revenue"]["values"][0]["page"]
    assert validate_pack(example) == []


def test_v110_published_value_requires_page_and_raw_text(example: dict[str, Any]) -> None:
    pack = as_v110(example)
    value = pack["items"]["revenue"]["values"][0]
    del value["page"]
    value["raw_text"] = None
    errors = validate_pack(pack)
    assert any("'page' is a required property" in e for e in errors)
    assert any("raw_text" in e for e in errors)


def test_v110_null_value_needs_no_page(example: dict[str, Any]) -> None:
    pack = as_v110(example)
    pack["items"]["revenue"]["values"][0] = {"period_id": "2024", "value": None, "confidence": 0.0}
    assert validate_pack(pack) == []


def test_v110_derived_value_requires_components(example: dict[str, Any]) -> None:
    pack = as_v110(example)
    value = pack["items"]["total_debt"]["values"][0]
    value.update({"engine": "derived", "raw_text": None, "page": None})
    assert any("derived_from" in e for e in validate_pack(pack))
    value["derived_from"] = [
        {"item": "borrowings_current", "period_id": "2024"},
        {"item": "lease_liabilities_current", "period_id": "2024", "assumed_zero": True},
    ]
    value["derivation"] = "sum"
    assert validate_pack(pack) == []


def test_unknown_warning_code_is_rejected(example: dict[str, Any]) -> None:
    example["warnings"].append({"code": "looks_fine", "message": "no"})
    assert validate_pack(example)


def test_extra_top_level_field_is_rejected(example: dict[str, Any]) -> None:
    example["guessed_revenue"] = 1.0
    assert validate_pack(example)
