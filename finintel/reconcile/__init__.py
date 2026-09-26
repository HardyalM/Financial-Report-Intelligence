"""Anchoring, cross-family voting, arithmetic checks and publication (EXTRACTION section 5)."""

from dataclasses import dataclass
from typing import Any

from finintel._placeholders import not_yet
from finintel.contracts import StatementPack


@dataclass(frozen=True)
class ExtractionReport:
    """Every candidate, anchoring result, check and decision. Fields are defined in M2.5."""


def reconcile(candidates: Any) -> tuple[StatementPack, ExtractionReport]:
    """Publish only anchored, deterministic candidates at or above tau; everything else is null."""
    not_yet("M2.4", "reconcile")
