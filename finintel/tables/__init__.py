"""StatementTables: rows, number grammar, units, currency and periods (EXTRACTION 2-4.2)."""

from dataclasses import dataclass
from typing import Any

from finintel._placeholders import not_yet


@dataclass(frozen=True)
class StatementTable:
    """Rows and columns of one statement from one engine. Fields are defined in M2.2."""


def build_statement_tables(parsed: Any, locations: Any) -> list[StatementTable]:
    """Build StatementTables aligned to text-layer lines (M2.2) with header semantics (M2.3)."""
    not_yet("M2.2", "build_statement_tables")
