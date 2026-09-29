"""Document type and balance-sheet classification (EXTRACTION section 1.4).

Decided from what the located statements actually present, never from a label or a company name.
The classified-balance-sheet test decides current-ratio applicability for every document type.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from finintel.locate.models import DocumentProfile, DocumentType
from finintel.locate.signals import PageView

_CURRENT_ASSETS = re.compile(r"^(?:total\s+)?current assets\b")
_CURRENT_LIABILITIES = re.compile(
    r"^(?:total\s+)?current liabilities\b|^creditors:?\s+amounts falling due within one year\b"
)
_REVENUE = re.compile(
    r"^(?:group\s+|total\s+)?(?:revenue|turnover)\b|^revenue from contracts with customers\b"
)
_NHS_TITLE = re.compile(r"\bnhs\b|department of health and social care")


def profile_document(
    income_statement: Sequence[PageView],
    balance_sheet: Sequence[PageView],
    statement_titles: Sequence[str],
) -> DocumentProfile:
    """Profile from the located income statement and balance sheet pages (empty if not found)."""
    bs_lines = [line.norm for view in balance_sheet for line in view.lines]
    is_lines = [line.norm for view in income_statement for line in view.lines]
    bs_text, is_text = " ".join(bs_lines), " ".join(is_lines)

    classified: bool | None = None
    evidence: dict[str, tuple[str, ...]] = {}
    if balance_sheet:
        assets = [line for line in bs_lines if _CURRENT_ASSETS.match(line)]
        liabilities = [line for line in bs_lines if _CURRENT_LIABILITIES.match(line)]
        classified = bool(assets and liabilities)
        evidence["classified"] = tuple(assets[:1] + liabilities[:1]) or (
            "no current/non-current split",
        )

    bank = [
        signal
        for signal, present in (
            ("loans and advances to customers", "loans and advances to customers" in bs_text),
            (
                "customer deposits",
                "customer deposits" in bs_text or "deposits from customers" in bs_text,
            ),
            ("net interest income", "net interest income" in is_text),
        )
        if present
    ]
    nhs = [
        signal
        for signal, present in (
            ("public dividend capital", "public dividend capital" in bs_text),
            ("taxpayers' equity", "taxpayers' equity" in bs_text),
            (
                "NHS in statement titles",
                any(_NHS_TITLE.search(t.lower()) for t in statement_titles),
            ),
            (
                "operating income from patient care activities",
                "operating income from patient care activities" in is_text,
            ),
        )
        if present
    ]
    revenue = [line for line in is_lines if _REVENUE.match(line)]
    evidence["bank"] = tuple(bank)
    evidence["nhs"] = tuple(nhs)
    evidence["revenue"] = tuple(revenue[:1])

    is_bank, is_nhs = len(bank) == 3, len(nhs) >= 2
    # A partial bank profile conflicts with "corporate" (a retailer with a banking subsidiary
    # prints loans and advances to customers). Customer deposits alone do not: housebuilders and
    # retailers take deposits from customers as ordinary liabilities.
    bank_like = "loans and advances to customers" in bank or len(bank) >= 2
    if is_bank and not is_nhs:
        kind = DocumentType.BANK
    elif is_nhs and not is_bank:
        kind = DocumentType.NHS_TRUST
    elif classified and revenue and not bank_like and not nhs:
        kind = DocumentType.CORPORATE
    else:
        kind = DocumentType.OTHER
    return DocumentProfile(
        document_type=kind, balance_sheet_classified=classified, evidence=evidence
    )
