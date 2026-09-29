"""M2.1 gate: the synthetic layout specs locate exactly as their `expect` blocks say (ADR-010)."""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.synthetic.spec import SpecError, all_specs, check_spec, load_spec
from tests.locate.builders import locate_spec

SPECS = all_specs()
REQUIRED = {"company_before_group", "two_page_balance_sheet", "liquidity_ordered_insurer"}


def test_the_required_m2_1_specs_exist() -> None:
    assert {p.stem for p in SPECS} >= REQUIRED


@pytest.mark.parametrize("path", SPECS, ids=[p.stem for p in SPECS])
def test_spec_locates_as_expected(path: Path, tmp_path: Path) -> None:
    spec = load_spec(path)
    result = locate_spec(spec, tmp_path)

    for kind, expected in spec.expect.statements.items():
        location = next(loc for k, loc in result.statements.items() if k.value == kind)
        assert location.status == "found", (kind, result.warnings)
        assert location.pages == expected.pages
        assert location.scope is not None and location.scope.value == expected.scope
        if spec.expect.folio_offset is not None:
            assert location.page_labels == tuple(
                str(p - spec.expect.folio_offset) for p in expected.pages
            )
    for rejection in spec.expect.rejected:
        [candidate] = [
            c for c in result.candidates
            if c.page == rejection.page and c.statement_type.value == rejection.statement
        ]  # fmt: skip
        assert candidate.scope.value == rejection.scope
        assert candidate.excluded is not None and not candidate.selected
    assert result.profile.document_type.value == spec.expect.document_type
    assert result.profile.balance_sheet_classified is spec.expect.balance_sheet_classified
    assert result.folio_offset == spec.expect.folio_offset


def test_a_subtotal_that_does_not_add_up_is_refused() -> None:
    spec = load_spec(next(p for p in SPECS if p.stem == "company_before_group"))
    data = spec.model_dump()
    rows = data["pages"][2]["rows"]  # the consolidated income statement
    rows[4]["values"] = ["1,601", "1,480"]  # operating profit off by one
    with pytest.raises(SpecError, match="components sum to 1600"):
        check_spec(type(spec).model_validate(data))


def test_expectations_must_point_at_statement_pages() -> None:
    spec = load_spec(next(p for p in SPECS if p.stem == "two_page_balance_sheet"))
    data = spec.model_dump()
    data["expect"]["statements"]["balance_sheet"]["pages"] = [2]
    with pytest.raises(SpecError, match="not a balance_sheet page"):
        check_spec(type(spec).model_validate(data))
