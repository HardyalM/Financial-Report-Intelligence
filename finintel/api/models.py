"""Request and response models of the HTTP API (the OpenAPI document is generated from these)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorBody(_Model):
    code: str
    message: str


class UploadOut(_Model):
    id: int
    sha256: str
    status: str
    duplicate: bool = Field(description="True when this exact file was uploaded before.")


class JobOut(_Model):
    stage: str
    status: str
    attempts: int
    error_code: str | None


class ReportOut(_Model):
    id: int
    sha256: str
    filename: str
    page_count: int
    document_type: str
    status: str
    pack_version: int | None
    pack_sha: str | None
    pack: dict[str, Any] | None = Field(
        description="The StatementPack (schemas/statement_pack.schema.json)."
    )
    ratios: dict[str, Any] | None = Field(
        description="The RatioPack (schemas/ratio_pack.schema.json)."
    )
    warnings: list[dict[str, Any]]
    reduced_verification: bool
    stale: bool = Field(description="Existing commentary no longer matches the current pack.")
    jobs: list[JobOut]
    extraction: dict[str, Any] | None = Field(
        default=None,
        description="Read-only view of the extraction report: per-value candidates with the engine "
        "families that agreed, arithmetic checks, statement locations, and the labels searched for "
        "items that stayed null (finintel/api/extraction_view.py).",
    )


class CommentaryOut(_Model):
    id: int
    output: dict[str, Any] = Field(description="schemas/commentary.schema.json")
    stale: bool
    model_id: str | None
    prompt_version: str | None
    validation: dict[str, Any]


class PageWord(_Model):
    text: str
    bbox: tuple[float, float, float, float]


class PageOut(_Model):
    page: int
    label: str | None
    width: float
    height: float
    rotation: int
    text: str
    words: list[PageWord]


class ReviewItemOut(_Model):
    id: int
    item: str | None
    period_id: str | None
    kind: str
    status: str
    candidates: list[dict[str, Any]]


class ReviewOut(_Model):
    status: str
    items: list[ReviewItemOut]
    warnings: list[dict[str, Any]]


class OverrideIn(_Model):
    action: Literal["accept_candidate", "set_value", "set_null"]
    item: str
    period_id: str
    candidate_id: str | None = None
    value: float | None = None
    raw_text: str | None = None
    page: int | None = None
    reason: str | None = None
    force: bool = False


class OverrideOut(_Model):
    id: int
    action: str
    anchored: bool
    reason: str | None
    payload: dict[str, Any]
    created_at: str


class OverrideResult(_Model):
    override_id: int
    anchored: bool
    pack_version: int
    pack_sha: str
    ratios_recomputed: bool
    stale: bool
    warning_codes: list[str]


class UnitConfirmationIn(_Model):
    currency: str = Field(min_length=3, max_length=3)
    unit_scale: Literal[1, 1000, 1000000, 1000000000]
    evidence_page: int = Field(ge=1)


class StatementLocationIn(_Model):
    statement_type: Literal[
        "income_statement",
        "balance_sheet",
        "comprehensive_income",
        "cash_flow",
        "changes_in_equity",
    ]
    page: int = Field(ge=1)


class DocumentTypeIn(_Model):
    document_type: Literal["corporate", "bank", "nhs_trust", "other"]
    reason: str = Field(min_length=1)


class StatusOut(_Model):
    id: int
    status: str
    reran: list[str] = Field(description="Stages queued again by this decision.")


class HealthOut(_Model):
    status: str
    checks: dict[str, str] = Field(default_factory=dict)
