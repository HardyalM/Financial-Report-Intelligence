"""LLM provider port and the number-blind mapping pointer (EXTRACTION section 4.4, ADR-005/007).

The model sees row labels, sections, indentation and styles with every digit masked, and returns a
row id per requested item. Its output type has no numeric field (extra fields are refused), code
re-checks that the row exists in the right statement and survives the exclusion filter, and the
result is a *review suggestion* at fixed confidence 0.70: it never reaches a StatementPack.

Only a provider adapter may import a vendor SDK. M2.4 ships the port, the masking and validation,
and a scripted `FakeProvider` for tests. A live Anthropic adapter (OQ-9 = A) follows when a key is
configured; without one the pointer step is skipped and recorded, and the local path is unchanged.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from finintel.mapping.aliases import AliasSpec, normalise_label
from finintel.tables.models import StatementTable

PROMPT_VERSION = "pointer-1"
POINTER_CONFIDENCE = 0.70  # below tau by design: a suggestion can never publish
_DIGIT = re.compile(r"\d")


class LLMProvider(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str:
        """Return the model's reply text (expected to be JSON matching `PointerReply`)."""
        ...


class Pointer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    row_id: str | None
    reason: str = Field(max_length=300)


class PointerReply(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pointers: dict[str, Pointer]


class ReviewSuggestion(BaseModel):
    """A row the model points at. Labels and ids only: never a number."""

    model_config = ConfigDict(frozen=True)

    kind: str = "llm_suggestion"
    item: str
    row_id: str
    label: str
    page: int
    confidence: float = POINTER_CONFIDENCE
    reason: str
    prompt_version: str = PROMPT_VERSION


class FakeProvider:
    """Scripted replies for tests. No network, no vendor."""

    name = "fake"

    def __init__(self, reply: str | Mapping[str, object]) -> None:
        self.reply = reply if isinstance(reply, str) else json.dumps(reply)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.reply


def mask_digits(text: str) -> str:
    return _DIGIT.sub("#", text)


def masked_rows(table: StatementTable) -> list[dict[str, object]]:
    """Rows as the model sees them. Only figure rows carry a count of columns, never values."""
    return [
        {
            "row_id": r.row_id,
            "label": mask_digits(r.label_text),
            "section": mask_digits(r.section_header or ""),
            "indent": r.indent_level,
            "style": r.style.value,
            "has_figures": bool(r.cells),
            "page": r.page,
        }
        for r in table.rows
    ]


SYSTEM = (
    "You point at rows of a financial statement. You are shown row labels, sections, "
    "indentation and styles with all digits masked. For each requested canonical item return "
    "the row_id that holds it, or null if none does. Return JSON only: "
    '{"pointers": {item: {"row_id": ..., "reason": ...}}}. Never return a number.'
)


def suggest_pointers(
    table: StatementTable,
    items: Sequence[str],
    specs: Mapping[str, AliasSpec],
    provider: LLMProvider,
) -> tuple[list[ReviewSuggestion], list[str]]:
    """(suggestions, rejections). A reply that fails the schema is rejected whole."""
    wanted = [i for i in items if i in specs and specs[i].statement is table.statement_type]
    if not wanted:
        return [], []
    user = json.dumps(
        {
            "document_statement": table.statement_type.value,
            "items": wanted,
            "rows": masked_rows(table),
        }
    )
    raw = provider.complete(SYSTEM, user)
    try:
        reply = PointerReply.model_validate_json(raw)
    except ValidationError as exc:
        return [], [
            f"reply rejected by schema ({exc.error_count()} errors): "
            "only row ids and reasons are accepted"
        ]
    rows = {r.row_id: r for r in table.rows}
    suggestions: list[ReviewSuggestion] = []
    rejections: list[str] = []
    for item, pointer in reply.pointers.items():
        if item not in wanted or pointer.row_id is None:
            continue
        row = rows.get(pointer.row_id)
        if row is None or not row.cells:
            rejections.append(
                f"{item}: row {pointer.row_id!r} is not a figure row of this statement"
            )
        elif any(tok in normalise_label(row.label_text) for tok in specs[item].exclude_any):
            rejections.append(
                f"{item}: row {pointer.row_id} is excluded by the alias map (APM pattern)"
            )
        else:
            suggestions.append(
                ReviewSuggestion(
                    item=item,
                    row_id=row.row_id,
                    label=row.label_text,
                    page=row.page,
                    reason=pointer.reason,
                )
            )
    return suggestions, rejections
