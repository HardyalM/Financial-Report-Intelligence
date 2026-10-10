"""Header rules one at a time, on hand-built tables: units (SCHEMA section 7) and dates
(SCHEMA section 8). The accounting-sensitive cases are here: 52-week comparatives are never dated
by inference, "year ended" comparatives are, and a bare "$" needs a stated presentation currency."""

from __future__ import annotations

import pytest

from finintel.locate import StatementType
from finintel.parse.engines.base import EngineFamily
from finintel.tables.headers import assign_periods, decide_unit, presentation_currency
from finintel.tables.models import Column, ColumnKind, HeaderWord, StatementTable
from tests.locate.builders import Printed, layer, page

X = {"v1": (400.0, 430.0), "v2": (480.0, 510.0)}


def _table(headers: dict[str, list[str]], title: tuple[str, ...] = ()) -> StatementTable:
    """Value columns v1, v2 with the given header rows (one string per row, per column)."""
    words = [
        HeaderWord(
            page=1,
            row=row,
            text=text,
            bbox=(X[cid][1] - 5 * len(text), 100 + 10 * row, X[cid][1], 108 + 10 * row),
        )
        for cid, texts in headers.items()
        for row, text in enumerate(texts)
        if text
    ]
    columns = tuple(
        Column(
            column_id=cid,
            kind=ColumnKind.VALUE,
            header_text=" ".join(texts),
            x0=X[cid][0],
            x1=X[cid][1],
            evidence="",
        )
        for cid, texts in headers.items()
    )
    return StatementTable(
        statement_type=StatementType.INCOME_STATEMENT,
        scope=None,
        engine="test",
        engine_version="1",
        family=EngineFamily.TEXT_LAYER,
        pages=(1,),
        strategies={1: "text"},
        columns=columns,
        rows=(),
        title_block=title,
        header_words=tuple(words),
    )


DOC = layer([page([Printed("Body", 50, 300)])])


@pytest.mark.parametrize(
    ("token", "currency", "scale"),
    [
        ("£m", "GBP", 1_000_000), ("£ million", "GBP", 1_000_000), ("£mn", "GBP", 1_000_000),
        ("£'000", "GBP", 1_000), ("£000", "GBP", 1_000), ("£k", "GBP", 1_000),
        ("US$m", "USD", 1_000_000), ("US$ million", "USD", 1_000_000), ("US$000", "USD", 1_000),
        ("€m", "EUR", 1_000_000), ("€ million", "EUR", 1_000_000), ("EURm", "EUR", 1_000_000),
        ("€'000", "EUR", 1_000), ("£", "GBP", 1),
    ],
)  # fmt: skip
def test_unit_tokens(token: str, currency: str, scale: int) -> None:
    decision = decide_unit(_table({"v1": ["2025", token], "v2": ["2024", token]}), None)
    assert (decision.status, decision.currency, decision.unit_scale) == ("ok", currency, scale)


def test_two_different_units_block() -> None:
    decision = decide_unit(_table({"v1": ["2025", "£m"], "v2": ["2024", "£000"]}), None)
    assert decision.status == "needs_unit_confirmation" and "conflicting" in decision.evidence


def test_a_unit_in_the_title_block_counts() -> None:
    decision = decide_unit(
        _table({"v1": ["2025"], "v2": ["2024"]}, ("Income statement", "£ million")), None
    )
    assert decision.status == "ok" and decision.unit_scale == 1_000_000


def test_bare_dollar_needs_a_stated_presentation_currency() -> None:
    table = _table({"v1": ["2025", "$m"], "v2": ["2024", "$m"]})
    assert decide_unit(table, None).status == "currency_ambiguous"
    stated = layer(
        [
            page(
                [Printed("The presentation currency of the Group is US dollars.", 50, 300)],
                number=1,
            )
        ]
    )
    presentation = presentation_currency(stated)
    assert presentation == ("USD", 1)
    decision = decide_unit(table, presentation)
    assert (decision.status, decision.currency) == ("ok", "USD")


def _periods(
    headers: dict[str, list[str]], title: str
) -> dict[str, tuple[str | None, str | None, int | None]]:
    table, _, _ = assign_periods(_table(headers, ("Consolidated income statement", title)), DOC)
    return {c.column_id: (c.period_id, c.end_date, c.weeks) for c in table.columns}


def test_day_and_month_from_the_title_apply_to_every_year() -> None:
    got = _periods({"v1": ["2024"], "v2": ["2023"]}, "for the year ended 31 December")
    assert got == {"v1": ("FY2024", "2024-12-31", None), "v2": ("FY2023", "2023-12-31", None)}


def test_year_ended_dates_the_comparative() -> None:
    got = _periods({"v1": ["2025"], "v2": ["2024"]}, "For the year ended 31 March 2025")
    assert got["v2"] == ("FY2024", "2024-03-31", None)


def test_52_weeks_never_dates_the_comparative() -> None:
    got = _periods({"v1": ["2025"], "v2": ["2024"]}, "For the 52 weeks ended 29 March 2025")
    assert got["v1"] == ("FY2025", "2025-03-29", 52)
    assert got["v2"] == ("FY2024", None, None)  # 30 March or 1 April 2024? Not printed: null


def test_as_at_with_a_year_never_dates_the_comparative() -> None:
    got = _periods({"v1": ["2025"], "v2": ["2024"]}, "As at 29 March 2025")
    assert got["v2"] == ("FY2024", None, None)


def test_full_dates_in_the_columns_win() -> None:
    got = _periods(
        {"v1": ["29 March 2025"], "v2": ["30 March 2024"]}, "For the 52 weeks ended 29 March 2025"
    )
    assert got["v1"][:2] == ("FY2025", "2025-03-29") and got["v2"][:2] == ("FY2024", "2024-03-30")


def test_fiscal_year_labels() -> None:
    got = _periods({"v1": ["2024/25"], "v2": ["2023/24"]}, "for the year ended 31 March")
    assert got == {"v1": ("FY2025", "2025-03-31", None), "v2": ("FY2024", "2024-03-31", None)}


def test_a_column_without_a_period_is_excluded_with_a_warning() -> None:
    table, _, warnings = assign_periods(_table({"v1": ["2025"], "v2": ["Movement"]}, ("x",)), DOC)
    [v2] = [c for c in table.columns if c.column_id == "v2"]
    assert v2.excluded == "no period in the column header" and not v2.usable
    assert [w.code for w in warnings] == ["period_ambiguous"]


def test_two_columns_for_one_period_without_a_total_are_ambiguous() -> None:
    table, _, warnings = assign_periods(
        _table({"v1": ["2025", "Underlying"], "v2": ["2025", "Adjusted"]}), DOC
    )
    assert all(c.excluded for c in table.columns)
    assert [w.code for w in warnings] == ["period_ambiguous"]


def _grouped_table() -> StatementTable:
    """Tesco's income statement header (company_c p.137), coordinates as printed: per year three
    columns (before adjusting items, adjusting items, total) under one date that happens to end
    within 3 pt of the middle column's right edge."""
    cols = {"v1": (469.3, 496.1), "v2": (535.5, 552.9), "v3": (582.6, 609.4),
            "v4": (644.1, 670.4), "v5": (709.8, 727.2), "v6": (757.2, 783.8)}  # fmt: skip
    printed = [  # (row, x0, x1, text)
        (0, 503.5, 548.2, "52 weeks ended"), (0, 678.8, 721.6, "52 weeks ended"),
        (1, 501.4, 550.2, "22 February 2025"), (1, 676.8, 723.5, "24 February 2024"),
        (2, 448.2, 493.9, "Before adjusting"), (2, 507.6, 550.6, "Adjusting items"),
        (2, 624.9, 668.3, "Before adjusting"), (2, 684.4, 725.0, "Adjusting items"),
        (3, 478.3, 493.9, "items"), (3, 528.9, 550.6, "(Note 5)"), (3, 593.6, 607.3, "Total"),
        (3, 653.5, 668.3, "items"), (3, 704.1, 725.0, "(Note 5)"), (3, 768.7, 781.6, "Total"),
    ]  # fmt: skip
    words = []
    for row, x0, x1, text in printed:
        parts = text.split()
        step = (x1 - x0) / len(parts)
        for i, part in enumerate(parts):
            words.append(HeaderWord(page=1, row=row, text=part,
                                    bbox=(x0 + i * step, 100 + 10 * row,
                                          x1 if i == len(parts) - 1 else x0 + (i + 1) * step - 1,
                                          108 + 10 * row)))  # fmt: skip
    columns = tuple(
        Column(column_id=cid, kind=ColumnKind.VALUE, header_text="", x0=x0, x1=x1, evidence="")
        for cid, (x0, x1) in cols.items()
    )
    return StatementTable(
        statement_type=StatementType.INCOME_STATEMENT, scope=None, engine="test",
        engine_version="1", family=EngineFamily.TEXT_LAYER, pages=(1,), strategies={1: "text"},
        columns=columns, rows=(), title_block=("Group income statement",),
        header_words=tuple(words),
    )  # fmt: skip


def test_a_date_over_a_group_of_columns_dates_the_whole_group() -> None:
    """company_c regression: the date was taken as the middle column's own header, so the
    adjusting-items column became "the year" and revenue was published as 0 (RESULTS.md)."""
    table, periods, warnings = assign_periods(_grouped_table(), DOC)
    by_id = {c.column_id: c for c in table.columns}
    assert [by_id[c].period_id for c in ("v1", "v2", "v3")] == ["FY2025"] * 3
    assert [by_id[c].period_id for c in ("v4", "v5", "v6")] == ["FY2024"] * 3
    used = sorted(c.column_id for c in table.columns if c.usable)
    assert used == ["v3", "v6"]  # only the statutory Total of each year
    assert {p.id: p.end_date for p in periods} == {"FY2025": "2025-02-22", "FY2024": "2024-02-24"}
    assert not [w for w in warnings if w.code == "period_ambiguous"]
