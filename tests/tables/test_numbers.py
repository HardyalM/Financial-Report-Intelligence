"""Number grammar (EXTRACTION section 4.2). Gate: a dash is 0; "n/a" stays unparsed (never 0);
brackets are negative; footnote markers are stripped."""

from __future__ import annotations

from decimal import Decimal

import pytest

from finintel.tables.numbers import canonical, parse_number


@pytest.mark.parametrize(
    ("raw", "value", "decimals"),
    [
        ("13,907.5", Decimal("13907.5"), 1),
        ("60,761", Decimal("60761"), 0),
        ("(1,234)", Decimal("-1234"), 0),
        ("(1,234.56)", Decimal("-1234.56"), 2),
        ("-12", Decimal("-12"), 0),
        ("\u201312", Decimal("-12"), 0),  # en dash used as a minus
        ("\u221212.5", Decimal("-12.5"), 1),  # Unicode minus
        ("£907.5", Decimal("907.5"), 1),
        ("(£1,234)", Decimal("-1234"), 0),
        ("-£1,234", Decimal("-1234"), 0),
        ("US$1,000", Decimal("1000"), 0),
        ("13\u2009907", Decimal("13907"), 0),  # thin-space thousands separator
        ("1\u202f234\u202f567", Decimal("1234567"), 0),
        ("0", Decimal("0"), 0),
        ("  2,335  ", Decimal("2335"), 0),
    ],
)
def test_numbers(raw: str, value: Decimal, decimals: int) -> None:
    parsed = parse_number(raw)
    assert parsed is not None
    assert parsed.value == value and parsed.decimals == decimals


@pytest.mark.parametrize("raw", ["-", "\u2013", "\u2014", "nil", "Nil", " \u2013 "])
def test_a_dash_or_nil_is_zero(raw: str) -> None:
    parsed = parse_number(raw)
    assert parsed is not None and parsed.value == 0 and parsed.nil


@pytest.mark.parametrize(
    "raw",
    ["n/a", "N/A", "see note 12", "12.5%", "£13.9bn", "6.3p", "1,23", "12,34,567", "(493",
     "22,311 18,590", "1 234", "", "   ", "(\u2013)", "abc", "2024a", "--5"],
)  # fmt: skip
def test_anything_else_stays_unparsed(raw: str) -> None:
    assert parse_number(raw) is None
    assert parse_number(None) is None


def test_brackets_are_negative_and_say_so() -> None:
    parsed = parse_number("(9,400)")
    assert parsed is not None and parsed.value == Decimal("-9400")
    assert parsed.negative_style == "brackets"


@pytest.mark.parametrize(
    ("raw", "value", "footnote"),
    [
        ("1,234*", Decimal("1234"), "*"),
        ("1,234\u2020", Decimal("1234"), "\u2020"),
        ("(1,234)\u2021", Decimal("-1234"), "\u2021"),
        ("1,234\u00b9", Decimal("1234"), "\u00b9"),  # not 12,341: stripped before NFKC
        ("7,140\u00b2\u00b3", Decimal("7140"), "\u00b2\u00b3"),
    ],
)
def test_footnote_markers_are_stripped_not_read_as_digits(
    raw: str, value: Decimal, footnote: str
) -> None:
    parsed = parse_number(raw)
    assert parsed is not None and parsed.value == value and parsed.footnote == footnote


@pytest.mark.parametrize(
    ("a", "b"),
    [("(1,234)", "-1234"), ("\u22121,234", "(1,234)"), ("13,907.50", "13907.5"), ("\u2013", "0"),
     ("nil", "-"), ("1,000", "1000")],
)  # fmt: skip
def test_canonical_form_unifies_printing_styles(a: str, b: str) -> None:
    assert canonical(a) == canonical(b)


def test_canonical_keeps_unparsed_text() -> None:
    assert canonical("n/a") == "n/a" and canonical("6.3p") == "6.3p"
    assert canonical("(1,234)") != canonical("1,234")
