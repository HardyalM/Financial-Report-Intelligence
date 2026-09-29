"""Contracts for statement location and the document profile (EXTRACTION sections 1-2).

Internal, not locked: they feed `ExtractionReport` and the review UI. Every decision carries its
evidence (signals, scope source, exclusion reason), so a reviewer can see why a page was chosen or
rejected without re-running anything.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class StatementType(StrEnum):
    INCOME_STATEMENT = "income_statement"
    COMPREHENSIVE_INCOME = "comprehensive_income"
    BALANCE_SHEET = "balance_sheet"
    CASH_FLOW = "cash_flow"
    CHANGES_IN_EQUITY = "changes_in_equity"


#: Statements v1 extracts. The others are located for continuity and later use only.
EXTRACTED = (StatementType.INCOME_STATEMENT, StatementType.BALANCE_SHEET)


class Scope(StrEnum):
    GROUP = "group"  # consolidated
    COMPANY = "company"  # parent company only: never a v1 value source
    MIXED = "group_and_company"  # Group | Company columns side by side (M2.3 picks the columns)
    SINGLE_ENTITY = "single_entity"  # one set of statements, no qualifier (typical of NHS trusts)
    UNKNOWN = "unknown"


SELECTABLE_SCOPES = (Scope.GROUP, Scope.MIXED, Scope.SINGLE_ENTITY)


class DocumentType(StrEnum):
    CORPORATE = "corporate"
    BANK = "bank"
    NHS_TRUST = "nhs_trust"
    OTHER = "other"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Signal(_Frozen):
    """One scoring signal (EXTRACTION section 1.1). `detail` says what was seen."""

    name: str
    weight: float
    hit: bool
    detail: str


class PageCandidate(_Frozen):
    """A page scored for one statement type, selected or not."""

    page: int
    page_label: str | None
    statement_type: StatementType
    title: str | None
    continued: bool = False  # the title says "continued"
    scope: Scope
    scope_evidence: str
    score: float
    signals: tuple[Signal, ...]
    excluded: str | None = None  # hard exclusion or scope reason; None when selectable
    selected: bool = False


class Continuation(_Frozen):
    """Why page `page` continues the statement on the page before it (EXTRACTION section 2)."""

    page: int
    value_columns: int
    evidence: str


class StatementLocation(_Frozen):
    statement_type: StatementType
    status: str  # "found", "ambiguous" or "not_found"
    scope: Scope | None = None
    pages: tuple[int, ...] = ()
    page_labels: tuple[str | None, ...] = ()
    title: str | None = None
    score: float | None = None
    continuations: tuple[Continuation, ...] = ()
    spread: bool = False
    #: Set when a combined statement of comprehensive income stands in for the income statement.
    source_type: StatementType | None = None


class DocumentProfile(_Frozen):
    """EXTRACTION section 1.4: decided by what the statements present, not by a label."""

    document_type: DocumentType
    balance_sheet_classified: bool | None  # None when no balance sheet was located
    evidence: dict[str, tuple[str, ...]]


class LocateWarning(_Frozen):
    code: str
    message: str
    page: int | None = None
    statement: StatementType | None = None


class LocateResult(_Frozen):
    locator_version: str
    page_count: int
    folio_offset: int | None  # printed folio = PDF page - offset, when folios are printed
    statements: dict[StatementType, StatementLocation]
    candidates: tuple[PageCandidate, ...]
    profile: DocumentProfile
    warnings: tuple[LocateWarning, ...]

    def location(self, statement_type: StatementType) -> StatementLocation:
        return self.statements[statement_type]
