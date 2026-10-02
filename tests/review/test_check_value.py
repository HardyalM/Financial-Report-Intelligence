"""An override value is the printed number in the item's canonical sign (SCHEMA section 4.2)."""

from __future__ import annotations

import pytest

from finintel.reconcile.pack import LIABILITY_ITEMS
from finintel.review.overrides import OverrideError, check_value


def refused(item: str, value: float, raw_text: str) -> str:
    with pytest.raises(OverrideError) as exc:
        check_value(item, value, raw_text)
    assert exc.value.status == 422
    return exc.value.code


@pytest.mark.parametrize("item", sorted(LIABILITY_ITEMS))
def test_a_bracketed_liability_is_accepted_as_a_positive_magnitude(item: str) -> None:
    check_value(item, 3300.0, "(3,300)")
    check_value(item, 3300.0, "3,300")
    check_value(item, 3300.0, "-3,300")


def test_a_bracketed_liability_with_the_wrong_digits_is_refused() -> None:
    assert refused("current_liabilities", 3200.0, "(3,300)") == "value_does_not_match_raw_text"


def test_a_liability_is_never_stored_negative() -> None:
    with pytest.raises(OverrideError, match=r"reads as 3300.0 for current_liabilities"):
        check_value("current_liabilities", -3300.0, "(3,300)")


def test_a_bracketed_loss_still_requires_the_negative_value() -> None:
    check_value("operating_profit", -120.0, "(120)")
    assert refused("operating_profit", 120.0, "(120)") == "value_does_not_match_raw_text"


def test_bracketed_negative_equity_still_requires_the_negative_value() -> None:
    check_value("total_equity", -350.0, "(350)")
    assert refused("total_equity", 350.0, "(350)") == "value_does_not_match_raw_text"


def test_text_that_is_not_a_printed_figure_is_refused_for_any_item() -> None:
    assert refused("current_liabilities", 0.0, "n/a") == "raw_text_not_a_number"
    assert refused("current_liabilities", 0.0, "\u2013") == "raw_text_not_a_number"
