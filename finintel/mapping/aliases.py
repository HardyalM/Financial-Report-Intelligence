"""Alias map loading and label normalisation (SCHEMA section 6)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from finintel.locate.models import StatementType
from finintel.locate.signals import normalise

ALIAS_DIR = Path(__file__).parent / "aliases"
_NOTE = re.compile(r"\((?:note|notes)\s*[\w.,\s]+\)")
_TRAILING_MARK = re.compile(r"(?:\s*\((?:[a-z]|\d{1,2}[a-z]?)\)|\s*[*†‡¹²³])+$")


def normalise_label(text: str) -> str:
    """Lower case, NFKC, straight quotes; note references, footnote markers and trailing colons
    stripped; "&" becomes "and"; whitespace collapsed. For matching only, never for storage."""
    text = re.sub(
        r"[\s*\u2020\u2021\u00b9\u00b2\u00b3]+$", "", text
    )  # before NFKC: "\u00b9" is not "1"
    label = normalise(text)
    label = _NOTE.sub("", label).replace("&", " and ")
    label = _TRAILING_MARK.sub("", " ".join(label.split()))
    return " ".join(label.split()).rstrip(": ")


@dataclass(frozen=True)
class AliasSpec:
    item: str
    statement: StatementType
    include_exact: frozenset[str]
    include_regex: tuple[re.Pattern[str], ...]
    exclude_any: tuple[str, ...]
    sections: frozenset[str] | None
    structural: frozenset[str]
    internal: bool


@cache
def load_aliases(document_type: str = "corporate") -> dict[str, AliasSpec]:
    raw: dict[str, Any] = yaml.safe_load((ALIAS_DIR / f"{document_type}.yaml").read_text("utf-8"))
    specs: dict[str, AliasSpec] = {}
    for item, body in raw.items():
        if item.startswith("_"):
            continue
        specs[item] = AliasSpec(
            item=item,
            statement=StatementType(body["statement"]),
            include_exact=frozenset(normalise_label(x) for x in body.get("include_exact", [])),
            include_regex=tuple(re.compile(x) for x in body.get("include_regex", [])),
            exclude_any=tuple(x.lower() for x in body.get("exclude_any", [])),
            sections=frozenset(normalise_label(x) for x in body["sections"])
            if "sections" in body
            else None,
            structural=frozenset(normalise_label(x) for x in body.get("structural", [])),
            internal=bool(body.get("internal", False)),
        )
    return specs
