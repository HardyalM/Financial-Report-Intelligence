"""Deterministic ratios: pure functions over a StatementPack, no I/O, no LLM (CLAUDE.md).

The locked formulas live in CLAUDE.md and are reproduced in code comments in M3, where a
drift test compares them with CLAUDE.md.
"""

from dataclasses import dataclass

from finintel._placeholders import not_yet
from finintel.contracts import StatementPack


@dataclass(frozen=True)
class RatioPack:
    """Replaced in M3 by the model generated from schemas/ratio_pack.schema.json."""


def compute_ratios(pack: StatementPack) -> RatioPack:
    """Compute the locked v1 ratios for every period in the pack."""
    not_yet("M3", "compute_ratios")
