"""Supplemental facts: figures the audited StatementPack does not carry (ADR-011, option A).

Basic EPS, free cash flow, underlying operating profit, a segment's operating profit and the
parent's investment in subsidiaries are real, printed numbers that the locked statement pack has no
item for. They live in a separate record, never in the pack and never feeding a ratio. Each fact
carries value, unit, currency, period, page, raw text and confidence, and says whether it is a
non-GAAP measure. They are read from the printed rows by label, with column and unit read from the
table's own header, never from a page number given in advance.
"""

from finintel.facts.extract import SPECS, FactSpec, extract_facts
from finintel.facts.models import FactWarning, SupplementalFact, SupplementalFacts

__all__ = [
    "SPECS",
    "FactSpec",
    "FactWarning",
    "SupplementalFact",
    "SupplementalFacts",
    "extract_facts",
]
