"""V3 quote matching after normalisation, with exact offsets; V5 allow-list details; schemas."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from finintel.commentary.validators import build_citation, locate_quote, naked_numbers
from finintel.commentary.validators.citations import QuoteError
from finintel.contracts import Citation
from tests.commentary.builders import ROOT, chunk

BASE = "Management said the group’s supply chain remained resilient – despite pressure."


def test_exact_quote_has_exact_offsets() -> None:
    m = locate_quote("one two three four five six", "three four five")
    assert m is not None and (m.start, m.end, m.exact) == (8, 23, True)


@pytest.mark.parametrize(
    ("text", "quote"),
    [
        (BASE, "the group's supply chain remained resilient - despite pressure"),  # curly, en dash
        (BASE, "the   group’s supply\nchain remained resilient – despite"),  # whitespace
        (
            "Our eﬃciency programme delivered ﬁve new plants",
            "efficiency programme delivered five new",
        ),
        ("Our supply- chain team", "supply-chain team"),  # a real compound split at a line end
        ("Our sup- ply planners", "supply planners"),  # a word split at a line end
        ("Our supply- chain team", "supplychain team"),
        ("A “strong” year with ‘steady’ growth overall", "A \"strong\" year with 'steady' growth"),
    ],
)
def test_normalised_quotes_match_and_map_back_to_the_original_text(text: str, quote: str) -> None:
    m = locate_quote(text, quote)
    assert m is not None and not m.exact
    original = text[m.start : m.end]
    assert original and original[0] != " " and original[-1] != " "
    assert text.startswith(original, m.start)


def test_offsets_cover_exactly_the_matched_source_characters() -> None:
    m = locate_quote(BASE, "group's supply chain remained resilient - despite")
    assert m is not None
    assert BASE[m.start : m.end] == "group’s supply chain remained resilient – despite"


def test_non_matches_are_none() -> None:
    assert locate_quote(BASE, "supply chain remained fragile") is None
    assert locate_quote(BASE, "") is None
    assert locate_quote("The Group grew", "the group grew") is None  # case is not normalised


def test_a_normalised_citation_is_marked_normalised() -> None:
    c = chunk("c", BASE)
    cite = build_citation(c, "the group's supply chain remained resilient", "cit_01", {57: "55"})
    assert cite.match == "normalised" and cite.page_label == "55" and cite.char_start > c.char_start
    with pytest.raises(QuoteError, match="quote_length"):
        build_citation(c, "supply chain", "cit_02")
    with pytest.raises(QuoteError, match="quote_not_in_chunk"):
        build_citation(c, "supply chain remained very fragile indeed", "cit_03")


def test_numbers_allowed_only_as_years_and_matching_notes() -> None:
    kw = {"allowed_years": ("2025", "2024")}
    assert naked_numbers("In 2025 against 2024 the group grew.", [], **kw) == []
    assert naked_numbers("In 2019 the group grew.", [], **kw) == ["2019"]
    assert naked_numbers("See note 12 for detail.", [], note_numbers=("12",)) == []
    assert naked_numbers("See note 13 for detail.", [], note_numbers=("12",)) == ["13"]
    assert naked_numbers("Twelve brands grew.", []) == ["Twelve"]
    assert naked_numbers("The first quarter and second quarter were soft.", []) == []
    assert naked_numbers("A quarter of sales were hit.", [])  # a fraction
    assert naked_numbers("Only one of the risks changed.", []) == []
    assert naked_numbers("One risk changed.", []) == ["One"]


def test_citation_schema_matches_the_schema_embedded_in_commentary() -> None:
    schemas = ROOT / "schemas"
    citation = json.loads((schemas / "citation.schema.json").read_text(encoding="utf-8"))
    commentary = json.loads((schemas / "commentary.schema.json").read_text(encoding="utf-8"))
    for key in ("$schema", "$id", "title", "description"):
        citation.pop(key)
    assert commentary["$defs"]["citation"] == citation


def test_a_citation_validates_against_its_schema() -> None:
    schema = json.loads((ROOT / "schemas" / "citation.schema.json").read_text(encoding="utf-8"))
    c = chunk("c", BASE)
    cite = build_citation(c, "the group's supply chain remained resilient", "cit_01")
    assert isinstance(cite, Citation)
    assert list(Draft202012Validator(schema).iter_errors(cite.model_dump(mode="json"))) == []


def test_the_commentary_schema_accepts_a_minimal_extractive_document() -> None:
    schema = json.loads((ROOT / "schemas" / "commentary.schema.json").read_text(encoding="utf-8"))
    doc: dict[str, object] = {
        "schema_version": "1.0.0", "mode": "extractive",
        "label": "Extractive summary: no generated text", "topics": [],
        "executive_summary": {"status": "omitted", "bullets": []}, "model": None,
        "prompt_version": None, "query_set_version": "1", "retrieval_set_id": None,
        "trace_id": None, "statement_pack_sha": "0" * 64, "ratio_pack_sha": "1" * 64,
        "disclaimer": "Research aid, not investment advice.",
    }  # fmt: skip
    assert list(Draft202012Validator(schema).iter_errors(doc)) == []
    assert list(Draft202012Validator(schema).iter_errors({**doc, "extra": 1}))


def test_no_validator_reads_a_model_supplied_page() -> None:
    src = Path(ROOT / "finintel" / "commentary" / "validators" / "validate.py").read_text()
    assert '["page"]' not in src and "'page'" not in src
