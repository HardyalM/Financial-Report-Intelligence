"""Validators V1-V8 as pure functions plus the topic-level policy (RAG section 4.4).

`validate_output` makes one pass over a model's raw output and reports; it never calls a model.
The caller (M5.2) retries once with `feedback(report)` and then calls `finalize`, which drops what
still fails. A topic left with no paragraph is `validation_failed`, and the UI says so.
"""

from finintel.commentary.validators.citations import QuoteError, build_citation
from finintel.commentary.validators.fields import mismatched_placeholders
from finintel.commentary.validators.lexicon import advice_terms, direction_violations
from finintel.commentary.validators.numbers import naked_numbers, unit_beside_placeholder
from finintel.commentary.validators.text import locate_quote, normalise
from finintel.commentary.validators.validate import (
    ParagraphReport,
    TopicReport,
    Violation,
    feedback,
    finalize,
    summary_evidence,
    validate_output,
)

__all__ = [
    "ParagraphReport",
    "QuoteError",
    "TopicReport",
    "Violation",
    "advice_terms",
    "build_citation",
    "direction_violations",
    "feedback",
    "finalize",
    "locate_quote",
    "mismatched_placeholders",
    "naked_numbers",
    "normalise",
    "summary_evidence",
    "unit_beside_placeholder",
    "validate_output",
]
