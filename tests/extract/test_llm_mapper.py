"""ADR-005/007: a model may point at a row; it never supplies a number and never publishes."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from finintel.llm import (
    POINTER_CONFIDENCE,
    FakeProvider,
    Pointer,
    PointerReply,
    mask_digits,
    masked_rows,
    suggest_pointers,
)
from finintel.mapping.aliases import AliasSpec, load_aliases, normalise_label
from finintel.mapping.mapper import map_item
from finintel.reconcile.pack import TAU
from tests.extract.helpers import run_spec, spec_data


@pytest.mark.parametrize(
    ("raw", "label"),
    [
        ("Operating profit (note 5)", "operating profit"),
        ("Revenue ¹", "revenue"),
        ("of which: disposal of group companies (a)", "of which: disposal of group companies"),
        ("Profit before tax & exceptional items", "profit before tax and exceptional items"),
        (
            "Creditors: amounts falling due within one year",
            "creditors: amounts falling due within one year",
        ),
        ("Borrowings:", "borrowings"),
        ("Shareholders\u2019  equity", "shareholders' equity"),
        ("Operating profit/(loss)", "operating profit/(loss)"),
        ("Taxation (6A)", "taxation"),
    ],
)
def test_label_normalisation(raw: str, label: str) -> None:
    assert normalise_label(raw) == label


def test_alias_map_is_configuration_and_covers_the_locked_inputs() -> None:
    specs = load_aliases("corporate")
    for item in (
        "revenue",
        "operating_profit",
        "current_assets",
        "current_liabilities",
        "total_assets",
        "total_equity",
    ):
        assert item in specs
    assert specs["non_current_liabilities"].internal and not specs["revenue"].internal
    assert "adjusted" in specs["operating_profit"].exclude_any


def test_the_exclusion_filter_vetoes_a_row_whatever_rule_found_it(tmp_path: Path) -> None:
    from evals.synthetic.render import render
    from evals.synthetic.spec import Spec
    from finintel.cache import StageCache
    from finintel.ingest import sha256_file
    from finintel.locate import locate
    from finintel.parse.cached import cached_text_layer
    from finintel.tables import statement_tables

    pdf = render(Spec.model_validate(spec_data("company_before_group")), tmp_path / "h.pdf")
    cache, sha = StageCache(tmp_path / "c"), sha256_file(pdf)
    layer, _ = cached_text_layer(pdf, sha, cache)
    tables = statement_tables(pdf, sha, layer, locate(layer), cache)
    table = next(by["pdfplumber"] for k, by in tables.items() if k.value == "income_statement")
    base = load_aliases("corporate")["operating_profit"]
    hostile = AliasSpec(**{**base.__dict__, "exclude_any": ("operating",)})
    assert map_item(table, base).row is not None
    assert map_item(table, hostile).row is None  # vetoed, not chosen by another rule


# ------------------------------------------------------------------------------ pointer


def test_the_model_sees_no_digits_in_labels() -> None:
    assert mask_digits("Note 15C: 2024 restated") == "Note ##C: #### restated"


def test_numeric_fields_in_a_reply_are_rejected_at_the_schema() -> None:
    for bad in (
        {"pointers": {"revenue": {"row_id": "141:1", "reason": "x", "value": 60761}}},
        {"pointers": {"revenue": {"row_id": "141:1", "reason": "x"}}, "revenue": 60761},
        {"pointers": {"revenue": {"row_id": 60761, "reason": "x"}}},
    ):
        with pytest.raises(ValidationError):
            PointerReply.model_validate_json(json.dumps(bad))
    assert Pointer(row_id=None, reason="not on this statement").row_id is None


def _income_table(tmp_path: Path):  # type: ignore[no-untyped-def]
    from evals.synthetic.render import render
    from evals.synthetic.spec import Spec
    from finintel.cache import StageCache
    from finintel.ingest import sha256_file
    from finintel.locate import locate
    from finintel.parse.cached import cached_text_layer
    from finintel.tables import statement_tables

    data = spec_data("company_before_group")
    data["pages"][2]["rows"][0]["label"] = "Sales of goods"  # an unusual label the alias map lacks
    pdf = render(Spec.model_validate(data), tmp_path / "p.pdf")
    cache = StageCache(tmp_path / "cache")
    sha = sha256_file(pdf)
    layer, _ = cached_text_layer(pdf, sha, cache)
    tables = statement_tables(pdf, sha, layer, locate(layer), cache)
    return next(by["pdfplumber"] for k, by in tables.items() if k.value == "income_statement")


def test_a_rejected_reply_yields_no_suggestion(tmp_path: Path) -> None:
    table = _income_table(tmp_path)
    provider = FakeProvider(
        {"pointers": {"revenue": {"row_id": "3:1", "reason": "r", "value": 12500}}}
    )
    suggestions, rejections = suggest_pointers(
        table, ["revenue"], load_aliases("corporate"), provider
    )
    assert suggestions == [] and "rejected by schema" in rejections[0]


def test_a_valid_pointer_is_a_review_suggestion_at_fixed_confidence(tmp_path: Path) -> None:
    table = _income_table(tmp_path)
    row = table.rows[0]
    provider = FakeProvider(
        {"pointers": {"revenue": {"row_id": row.row_id, "reason": "first row is sales"}}}
    )
    [suggestion], rejections = suggest_pointers(
        table, ["revenue"], load_aliases("corporate"), provider
    )
    assert rejections == []
    assert (suggestion.item, suggestion.row_id, suggestion.label) == (
        "revenue",
        row.row_id,
        "Sales of goods",
    )
    assert suggestion.confidence == POINTER_CONFIDENCE < TAU
    assert "value" not in suggestion.model_dump() and "12,500" not in suggestion.model_dump_json()


def test_the_prompt_carries_no_printed_figure(tmp_path: Path) -> None:
    table = _income_table(tmp_path)
    provider = FakeProvider({"pointers": {}})
    suggest_pointers(table, ["revenue"], load_aliases("corporate"), provider)
    [(_, user)] = provider.calls
    for figure in ("12,500", "11,800", "(8,750)", "1,600"):
        assert figure not in user
    assert not re.search(r"\d,\d{3}", user)
    assert all(row["label"] == mask_digits(str(row["label"])) for row in masked_rows(table))


def test_pointers_for_unknown_rows_or_other_statements_are_rejected(tmp_path: Path) -> None:
    table = _income_table(tmp_path)
    provider = FakeProvider({"pointers": {"revenue": {"row_id": "999:1", "reason": "?"}}})
    suggestions, rejections = suggest_pointers(
        table, ["revenue", "total_equity"], load_aliases("corporate"), provider
    )
    assert suggestions == [] and "not a figure row" in rejections[0]


def test_suggestions_never_change_the_pack(tmp_path: Path) -> None:
    data = spec_data("company_before_group")
    data["pages"][2]["rows"][0]["label"] = "Sales of goods"
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    without = run_spec(data, tmp_path / "a")
    provider = FakeProvider(
        {"pointers": {"revenue": {"row_id": "3:1", "reason": "first row is sales"}}}
    )
    with_llm = run_spec(data, tmp_path / "b", provider=provider)
    assert without.pack is not None and with_llm.pack is not None
    for pack in (without.pack, with_llm.pack):
        pack["source"].pop("sha256")  # the PDFs were rendered separately (embedded timestamps)
    assert without.pack == with_llm.pack  # a suggestion never publishes
    assert (
        without.pack is not None and without.pack["items"]["revenue"]["values"][0]["value"] is None
    )
    assert without.report["review"]["llm"].startswith("skipped")
    [suggestion] = with_llm.report["review"]["suggestions"]
    assert suggestion["kind"] == "llm_suggestion" and suggestion["confidence"] == 0.70
