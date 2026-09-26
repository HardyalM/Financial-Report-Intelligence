"""Grounded commentary: placeholders, quotes and code-derived pages (RAG section 4)."""

from dataclasses import dataclass
from typing import Any

from finintel._placeholders import not_yet


@dataclass(frozen=True)
class Commentary:
    """Replaced in M5.1 by the model generated from schemas/commentary.schema.json."""


def generate_commentary(pack: Any, ratio_pack: Any, evidence: Any) -> Commentary:
    """Generate, validate (V1-V8), retry once, drop what still fails."""
    not_yet("M5.2", "generate_commentary")
