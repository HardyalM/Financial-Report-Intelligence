"""Append-only human overrides and pack re-materialisation (EXTRACTION section 6)."""

from dataclasses import dataclass

from finintel._placeholders import not_yet
from finintel.contracts import StatementPack


@dataclass(frozen=True)
class Override:
    """One reviewer action. Fields are defined in M6.2."""


def apply_overrides(pack: StatementPack, overrides: list[Override]) -> StatementPack:
    """Return a new pack version with overrides applied and marked."""
    not_yet("M6.2", "apply_overrides")
