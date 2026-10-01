"""Supplemental fact records. A fact is a number with its provenance; a null is a null."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Source(_Frozen):
    page: int
    raw_text: str  # the figure as printed, e.g. "6,932" or "€88,035m"
    row_text: str  # the printed row it came from


class SupplementalFact(_Frozen):
    id: str
    label: str
    entity: str  # "group" | "parent" | "segment:<name>"
    period_id: str
    value: float | None  # in `unit_scale` units; None when the figure could not be read safely
    unit_scale: int  # 1 for per-share figures, 1_000_000 for "million"
    currency: str | None
    per_share: bool
    is_apm: bool  # a non-GAAP / alternative performance measure
    page: int | None  # the page of the best (most precise) source
    raw_text: str | None
    confidence: float
    sources: tuple[Source, ...]  # every printed occurrence that agreed
    note: str | None = None  # why the value is null, when it is


class FactWarning(_Frozen):
    code: str  # "conflict" | "not_found" | "no_period" | "no_unit" | "rejected"
    fact: str
    message: str
    pages: tuple[int, ...] = ()


class SupplementalFacts(_Frozen):
    schema_version: str = "1.0.0"
    facts: tuple[SupplementalFact, ...]
    warnings: tuple[FactWarning, ...]

    def get(self, fact_id: str, period_id: str) -> SupplementalFact | None:
        return next((f for f in self.facts if f.id == fact_id and f.period_id == period_id), None)
