"""Numbers snapshot (RAG 4.3): one line rendered from templates in code, never by a model."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from finintel.commentary.render import TruthEntry, render_template
from finintel.contracts.ratio_pack import RatioPack

_SEGMENTS = (
    ("Revenue", "item", "revenue"),
    ("operating profit", "item", "operating_profit"),
    ("operating margin", "ratio", "operating_margin"),
    ("current ratio", "ratio", "current_ratio"),
    ("ROCE", "ratio", "roce"),
    ("debt-to-equity", "ratio", "debt_to_equity"),
)


def numbers_snapshot(ratios: RatioPack, truth: Mapping[str, TruthEntry]) -> dict[str, Any]:
    """The latest period against the prior one. A null shows its reason, never a guess."""
    if not ratios.periods:
        return {"template": "", "rendered": "", "period_id": None}
    latest = ratios.periods[0].period_id
    prior = ratios.periods[1].period_id if len(ratios.periods) > 1 else None
    parts = []
    for label, kind, ident in _SEGMENTS:
        value_key = f"{kind}:{ident}:{latest}"
        if value_key not in truth:
            continue
        part = f"{label} {{{{{value_key}}}}}"
        change_key = f"change:{kind}:{ident}:{prior}:{latest}"
        if prior and change_key in truth and truth[change_key].rendered is not None:
            part += f" ({{{{{change_key}}}}})"
        parts.append(part)
    template = "; ".join(parts) + "."
    return {
        "period_id": latest,
        "template": template,
        "rendered": render_template(template, truth),
    }
