"""Request and response models of the HTTP API (the OpenAPI document is generated from these)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from finintel.contracts.reported_metric import ReportedMetric


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


class ReportSummary(_Model):
    """One row of the report list: what the dashboard and the command palette show, no figures."""

    id: int
    filename: str
    company_name: str | None
    document_type: str
    status: str
    page_count: int
    created_at: str
    period_label: str | None = Field(description="The current period's label, e.g. FY2024.")
    currency: str | None
    unit_scale: int | None
    open_review_items: int = Field(description="Review items still waiting for a person.")
    stale: bool = Field(description="Existing commentary no longer matches the current pack.")
    is_sample: bool = Field(default=False, description="Sample data (removable as a set).")


class FigureCounts(_Model):
    """The current period's line items, by how each value was settled (no values here)."""

    read: int = Field(description="Read from the statements and anchored to the page.")
    derived: int = Field(description="Computed in code from printed lines (e.g. total debt).")
    manual: int = Field(description="Entered, forced or confirmed by a person.")
    empty: int = Field(description="Left empty, with the reason on the report.")


class RatioHeadline(_Model):
    name: str
    label: str
    value: float | None = Field(description="The ratio engine's value; null when not computed.")
    unit: Literal["fraction", "multiple"]
    status: str
    flags: list[str]
    change_kind: Literal["percentage_points", "absolute"] | None
    change: float | None = Field(description="Against the prior period, as the engine computed it.")


class CommentaryHeadline(_Model):
    mode: str
    topics_ok: int
    topics: int
    citations: int
    stale: bool


class ReportCard(_Model):
    """One report on the dashboard: what the pipeline produced for it, and what it waits for."""

    id: int
    title: str
    filename: str
    document_type: str
    status: str
    is_sample: bool
    created_at: str
    page_count: int
    period_label: str | None
    prior_label: str | None
    currency: str | None
    unit_scale: int | None
    figures: FigureCounts | None
    ratios: list[RatioHeadline]
    commentary: CommentaryHeadline | None
    open_review_items: int
    waiting_for: Literal["unit", "document_type", "review", "failed"] | None
    jobs: list[JobOut]


class DashboardOut(_Model):
    reports: list[ReportCard] = Field(description="Newest first.")
    has_samples: bool


class SamplesOut(_Model):
    added: list[int]
    skipped: list[int] = Field(description="Already present (never marked as samples).")
    removed: list[int]


class CommentaryOut(_Model):
    id: int
    output: dict[str, Any] = Field(description="schemas/commentary.schema.json")
    stale: bool
    model_id: str | None
    prompt_version: str | None
    validation: dict[str, Any]


class ReportedMetricsOut(_Model):
    metrics: list[ReportedMetric] = Field(
        description="schemas/reported_metric.schema.json: as stated in the report, never computed."
    )
    notes: list[str] = Field(
        description="Why a metric is not shown (the report disagrees with itself)."
    )


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
    # A figure is finite: NaN or Infinity (which JSON parsers accept) is refused here, before it
    # can reach a pack, a ratio or Postgres (which rejects NaN in jsonb).
    value: float | None = Field(default=None, allow_inf_nan=False)
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
