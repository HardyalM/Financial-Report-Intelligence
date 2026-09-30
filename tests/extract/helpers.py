"""Shared helpers: render a spec (or a modified copy of one), run the local pipeline."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from evals.synthetic.render import render
from evals.synthetic.spec import Spec, all_specs, load_spec
from finintel.cache import StageCache
from finintel.extract import ExtractionResult, extract_pack

SPEC_PATHS = {p.stem: p for p in all_specs()}


def spec_data(name: str) -> dict[str, Any]:
    return deepcopy(load_spec(SPEC_PATHS[name]).model_dump(mode="json"))


def run_spec(data: dict[str, Any] | Spec, tmp_path: Path, **kwargs: Any) -> ExtractionResult:
    spec = data if isinstance(data, Spec) else Spec.model_validate(data)
    pdf = render(spec, tmp_path / f"{spec.name}.pdf")
    return extract_pack(pdf, StageCache(tmp_path / "cache"), **kwargs)


def values(result: ExtractionResult, item: str) -> dict[str, float | None]:
    assert result.pack is not None
    return {v["period_id"]: v["value"] for v in result.pack["items"][item]["values"]}


def warnings(result: ExtractionResult, code: str, item: str | None = None) -> list[dict[str, Any]]:
    assert result.pack is not None
    return [
        w
        for w in result.pack["warnings"]
        if w["code"] == code and (item is None or w["item"] == item)
    ]


def bs_rows(data: dict[str, Any], page: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = data["pages"][page - 1]["rows"]
    return rows


def row_id(row: dict[str, Any]) -> str:
    return str(row.get("id") or "")
