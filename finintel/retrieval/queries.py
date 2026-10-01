"""Versioned topic query sets (RAG section 3.1). Variants are selected by `document_type`.

Configuration, not logic: the same report always gets the same queries. Bump QUERY_SET_VERSION
when any query or prior changes; it is persisted with the commentary.
"""

from __future__ import annotations

from dataclasses import dataclass

from finintel.locate.models import DocumentType

QUERY_SET_VERSION = "1"

TOPICS = ("revenue_drivers", "strategic_risks", "governance_and_directors", "liquidity_and_capital")
#: Omitted (not "insufficient_evidence") when its evidence floor is not met.
OPTIONAL_TOPICS = frozenset({"liquidity_and_capital"})


@dataclass(frozen=True)
class TopicQueries:
    topic: str
    queries: tuple[str, ...]
    priors: frozenset[str]


def _t(topic: str, queries: tuple[str, ...], priors: tuple[str, ...]) -> TopicQueries:
    return TopicQueries(topic, queries, frozenset(priors))


_CORPORATE = (
    _t("revenue_drivers", (
        "What drove revenue growth or decline in the year?",
        "Like-for-like sales performance by segment",
        "Pricing, volume and mix effects",
        "Performance of key divisions",
    ), ("ceo_review", "financial_review", "segment_review", "strategy")),
    _t("strategic_risks", (
        "Principal risks and uncertainties",
        "How the risk profile changed during the year",
        "Emerging risks",
        "Risk mitigations and risk appetite",
    ), ("principal_risks", "emerging_risks", "viability_statement")),
    _t("governance_and_directors", (
        "Going concern assessment and conclusion",
        "Viability statement period and scenarios",
        "Significant issues considered by the audit committee",
        "Key audit matters",
        "Board changes and directors' report disclosures",
    ), ("going_concern", "viability_statement", "audit_committee_report", "auditors_report",
        "directors_report", "notes_critical_judgements")),
    _t("liquidity_and_capital", (
        "Liquidity headroom and committed facilities",
        "Net debt and leverage",
        "Refinancing and debt maturity",
        "Covenants",
        "Capital allocation, dividends and buybacks",
    ), ("financial_review", "going_concern")),
)  # fmt: skip

_BANK = (
    _t("revenue_drivers", (
        "Net interest income and margin drivers",
        "Balance-sheet growth in lending and deposits",
        "Fee and commission income",
        "Impact of rates and hedging",
    ), ("ceo_review", "financial_review", "segment_review", "strategy")),
    _t("strategic_risks", (
        "Credit risk and expected credit losses",
        "Arrears and impairment",
        "Conduct and regulatory risk",
        "Operational and cyber resilience",
    ), ("principal_risks", "emerging_risks")),
    _t("governance_and_directors", (
        "Going concern",
        "Key audit matters (ECL and model risk)",
        "Board risk committee",
    ), ("going_concern", "audit_committee_report", "auditors_report", "directors_report")),
    _t("liquidity_and_capital", (
        "CET1 and capital position",
        "Liquidity coverage and net stable funding",
        "Funding and deposit mix",
    ), ("financial_review", "principal_risks")),
)  # fmt: skip

_NHS = (
    _t("revenue_drivers", (
        "Income against plan",
        "Patient-care income and contracts",
        "Elective recovery funding",
        "Other operating income",
    ), ("financial_review",)),
    _t("strategic_risks", (
        "Board assurance framework principal risks",
        "Quality and safety",
        "Workforce",
        "Financial sustainability",
    ), ("principal_risks",)),
    _t("governance_and_directors", (
        "Annual governance statement",
        "Significant control issues",
        "Head of internal audit opinion",
        "Going concern",
    ), ("going_concern", "auditors_report")),
    _t("liquidity_and_capital", (
        "Cash position",
        "Capital programme",
        "Public dividend capital and revenue support",
        "Deficit and efficiency programme",
    ), ("financial_review", "going_concern")),
)  # fmt: skip

# NHS priors: the taxonomy (narrative/sections.py) has no performance_report or
# accountability_report section yet, so those priors cannot be expressed.
# Added with the NHS alias work in M8.1.
_BY_TYPE = {
    DocumentType.CORPORATE: _CORPORATE,
    DocumentType.BANK: _BANK,
    DocumentType.NHS_TRUST: _NHS,
    # An unclassified document gets the corporate set: wording only, nothing numeric rides on it.
    DocumentType.OTHER: _CORPORATE,
}


def query_set(document_type: DocumentType) -> tuple[TopicQueries, ...]:
    return _BY_TYPE[document_type]
