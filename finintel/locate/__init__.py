"""Locate statement pages and profile the document (EXTRACTION section 1 and 1.4)."""

from dataclasses import dataclass
from typing import Any

from finintel._placeholders import not_yet


@dataclass(frozen=True)
class StatementLocation:
    """Statement type, scope, pages, score and signals. Fields are defined in M2.1."""


@dataclass(frozen=True)
class DocumentProfile:
    """Document type and whether the balance sheet is classified. Fields are defined in M2.1."""


def locate_statements(text_layer: Any) -> list[StatementLocation]:
    """Score pages and choose the consolidated statements."""
    not_yet("M2.1", "locate_statements")


def profile_document(text_layer: Any) -> DocumentProfile:
    """Decide document type and balance-sheet classification before mapping."""
    not_yet("M2.1", "profile_document")
