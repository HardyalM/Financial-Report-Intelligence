"""Deterministic mapping of rows to canonical items.

Number-blind LLM suggestions go to the review queue only (ADR-007).
"""

from dataclasses import dataclass
from typing import Any

from finintel._placeholders import not_yet


@dataclass(frozen=True)
class MappingCandidates:
    """Candidates per canonical item and period, with their method. Fields are defined in M2.4."""


def map_rows(tables: Any) -> MappingCandidates:
    """Alias map, then structural rules, then the exclusion filter."""
    not_yet("M2.4", "map_rows")
