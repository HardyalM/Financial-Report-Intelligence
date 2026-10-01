"""V9: a placeholder must be named by its own sentence (the placeholder-meaning guard).

Every placeholder is bound to a field (`item:current_assets:FY2024` -> current_assets, a change
placeholder to the field it changes). The sentence that carries it must name that field in words
("current assets"). A sentence that puts the current-assets placeholder after "solid progress" names
no field it can mean, and is rejected: validators V4-V8 prove a placeholder *exists*, this proves the
sentence says what the number *is*. A false positive costs a paragraph, never a mislabelled figure.
"""

from __future__ import annotations

import re
from collections.abc import Collection

from finintel.commentary.render import PLACEHOLDER

#: Words that name each field. Anything not listed is named by its own id ("cash", "total liabilities").
FIELD_NAMES: dict[str, tuple[str, ...]] = {
    "revenue": ("revenue", "turnover", "sales"),
    "operating_profit": ("operating profit", "operating income"),
    "profit_before_tax": ("profit before tax", "profit before taxation", "pre-tax profit", "pretax profit"),
    "net_income": ("net income", "net profit", "profit for the year", "profit after tax", "net earnings"),
    "current_assets": ("current assets",),
    "current_liabilities": ("current liabilities",),
    "total_assets": ("total assets",),
    "total_equity": ("total equity", "equity", "shareholders funds", "shareholders equity"),
    "total_debt": ("total debt", "debt", "borrowings"),
    "cash": ("cash", "cash and cash equivalents"),
    "borrowings_current": ("current borrowings", "short-term borrowings", "borrowings"),
    "borrowings_non_current": ("non-current borrowings", "long-term borrowings", "borrowings"),
    "lease_liabilities_current": ("current lease liabilities", "lease liabilities"),
    "lease_liabilities_non_current": ("non-current lease liabilities", "lease liabilities"),
    "total_liabilities": ("total liabilities",),
    "non_current_assets": ("non-current assets", "fixed assets"),
    "net_current_assets": ("net current assets",),
    "total_assets_less_current_liabilities": ("total assets less current liabilities", "capital employed"),
    "equity_attributable_to_owners": ("equity attributable", "attributable to owners", "shareholders equity"),
    "non_controlling_interests": ("non-controlling interests", "minority interests"),
    "operating_margin": ("operating margin",),
    "current_ratio": ("current ratio",),
    "debt_to_equity": ("debt-to-equity", "debt to equity", "gearing", "leverage"),
    "roce": ("roce", "return on capital employed"),
}  # fmt: skip
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _norm(text: str) -> str:
    return re.sub(r"[\s\-‐‑–—_'’]+", " ", text.lower()).strip()


def field_of(key: str) -> str | None:
    """The field a placeholder key is about: `item:cash:FY24` -> cash; a change -> its field."""
    parts = key.split(":")
    if parts[0] in ("item", "ratio") and len(parts) >= 3:
        return parts[1]
    if parts[0] == "change" and len(parts) >= 5:
        return parts[2]
    return None


def names_for(field: str) -> tuple[str, ...]:
    return FIELD_NAMES.get(field, (field.replace("_", " "),))


def mismatched_placeholders(template: str, known: Collection[str] | None = None) -> list[str]:
    """Placeholders whose sentence does not name their field. Unknown keys are V4's business."""
    problems: list[str] = []
    offset = 0
    for sentence in _SENTENCE.split(template):
        start = template.index(sentence, offset)
        offset = start + len(sentence)
        bare = _norm(PLACEHOLDER.sub(" ", sentence))
        for match in PLACEHOLDER.finditer(sentence):
            key = match.group(1)
            if known is not None and key not in known:
                continue
            field = field_of(key)
            if field is None:
                continue
            if not any(_norm(name) in bare for name in names_for(field)):
                problems.append(
                    f'{{{{{key}}}}} is not named in its sentence (say "{names_for(field)[0]}")'
                )
    return problems
