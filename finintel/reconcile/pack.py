"""Publish or null: candidates -> StatementPack + ExtractionReport (EXTRACTION sections 5.3-5.5).

Confidence is deterministic (never a model's opinion):
    base  = {exact_alias .95, regex_alias .90, structural .85}
    x 0.90 when only one engine family produced the cell (the two text-layer engines are one family)
    - 0.30 if any arithmetic check involving the cell fails, else + 0.05 if at least one passes
    capped at 0.99. Publish at >= tau (0.80); below it the value is null with `low_confidence`.
Engines of one family that read different cells give null + `parser_disagreement` (no tie-break in
M2.4; cross-family resolution is M2.5). An LLM suggestion is never a candidate here (ADR-007).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from finintel import PIPELINE_VERSION
from finintel.locate.models import LocateResult, StatementType
from finintel.mapping.aliases import AliasSpec
from finintel.mapping.mapper import METHOD_BASE, ItemMapping, map_table
from finintel.reconcile.checks import CheckResult, period_columns, run_checks
from finintel.tables.models import Cell, Row, StatementTable
from finintel.tables.numbers import canonical

TAU = 0.80
SINGLE_FAMILY = 0.90
CHECK_PASS, CHECK_FAIL, CAP = 0.05, 0.30, 0.99
REQUIRED = (
    "revenue", "operating_profit", "current_assets", "current_liabilities",
    "total_assets", "total_equity", "total_debt",
)  # fmt: skip
LIABILITY_ITEMS = frozenset(
    {"current_liabilities", "total_liabilities", "borrowings_current", "borrowings_non_current",
     "lease_liabilities_current", "lease_liabilities_non_current", "financial_liabilities_current",
     "financial_liabilities_non_current", "total_debt"}
)  # fmt: skip
DEBT_PARTS = (
    "borrowings_current",
    "borrowings_non_current",
    "lease_liabilities_current",
    "lease_liabilities_non_current",
)
_SECTION_CHECK = {
    "borrowings_current": "current_liabilities_section_sum",
    "lease_liabilities_current": "current_liabilities_section_sum",
    "borrowings_non_current": "non_current_liabilities_section_sum",
    "lease_liabilities_non_current": "non_current_liabilities_section_sum",
}
STATEMENT_OF = {
    StatementType.INCOME_STATEMENT: "income_statement",
    StatementType.BALANCE_SHEET: "balance_sheet",
}


@dataclass
class EngineView:
    engine: str
    tables: dict[StatementType, StatementTable]
    mapped: dict[str, ItemMapping] = field(default_factory=dict)
    checks: list[CheckResult] = field(default_factory=list)


@dataclass
class Resolution:
    item: str
    period_id: str
    value: float | None = None
    row: Row | None = None
    cell: Cell | None = None
    method: str | None = None
    confidence: float = 0.0
    engine: str | None = None
    derived_from: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    record: dict[str, Any] = field(default_factory=dict)

    def warn(self, code: str, message: str, page: int | None = None) -> None:
        self.warnings.append({"code": code, "message": message, "item": self.item, "page": page})


@dataclass
class Assembly:
    pack: dict[str, Any]
    report: dict[str, Any]


def _signed(item: str, value: Decimal) -> float:
    return float(abs(value) if item in LIABILITY_ITEMS else value)


def _confidence(method: str, checks: Sequence[CheckResult]) -> tuple[float, dict[str, Any]]:
    base = METHOD_BASE[method]
    value = base * SINGLE_FAMILY
    failed, passed = [c for c in checks if not c.passed], [c for c in checks if c.passed]
    value += -CHECK_FAIL if failed else (CHECK_PASS if passed else 0.0)
    final = round(min(CAP, value), 4)
    return final, {
        "base": base, "agreement": SINGLE_FAMILY,
        "checks_passed": [c.name for c in passed], "checks_failed": [
            f"{c.name}: {c.detail}, off by {c.difference}" for c in failed
        ],
        "confidence": final,
    }  # fmt: skip


def _resolve(
    item: str, period: str, views: Sequence[EngineView], kind: StatementType
) -> Resolution:
    res = Resolution(item, period)
    seen: dict[tuple[int, str], tuple[EngineView, Row, Cell, ItemMapping]] = {}
    weak = []
    for view in views:
        m = view.mapped.get(item)
        table = view.tables.get(kind)
        if m is None or table is None:
            continue
        if m.weak:
            weak.append((view.engine, [r.label_text for r in m.rivals]))
            continue
        column = period_columns(table).get(period)
        if m.row is None or column is None or column.column_id not in m.row.cells:
            continue
        cell = m.row.cells[column.column_id]
        seen.setdefault((cell.page, canonical(cell.raw_text)), (view, m.row, cell, m))
    res.record["engines"] = [v.engine for v in views if v.mapped.get(item)]
    if weak:
        res.warn(
            "alias_weak",
            f"several rows match {item} equally ({weak[0][1]}); none chosen, all go to review",
        )
        res.record["decision"] = "alias_weak"
        return res
    if not seen:
        res.record["decision"] = "no_candidate"
        return res
    if len(seen) > 1:
        shown = "; ".join(f"{v.engine}={c.raw_text} p.{c.page}" for v, _, c, _ in seen.values())
        res.warn("parser_disagreement", f"unresolved: {shown}", next(iter(seen.values()))[2].page)
        res.record.update(
            decision="parser_disagreement", candidates=[c.raw_text for _, _, c, _ in seen.values()]
        )
        return res
    view, row, cell, m = next(iter(seen.values()))
    assert m.method is not None
    checks = [c for c in view.checks if item in c.items and c.period_id == period]
    confidence, arithmetic = _confidence(m.method, checks)
    res.row, res.cell, res.method, res.engine, res.confidence = (
        row,
        cell,
        m.method,
        view.engine,
        confidence,
    )
    res.record.update(
        method=m.method,
        row=row.row_id,
        label=row.label_text,
        raw_text=cell.raw_text,
        page=cell.page,
        **arithmetic,
    )
    for c in checks:
        if not c.passed:
            res.warn(
                "arithmetic_check_failed",
                f"{c.name} for {period}: {c.detail}; off by {c.difference} "
                f"(tolerance {c.tolerance})",
                cell.page,
            )
    if cell.parsed_value is None:
        res.warn("low_confidence", f"printed {cell.raw_text!r} is not a number", cell.page)
        res.record["decision"] = "unparsed"
    elif confidence < TAU:
        res.warn("low_confidence", f"confidence {confidence} is below {TAU}", cell.page)
        res.record["decision"] = "below_threshold"
    else:
        res.value = _signed(item, cell.parsed_value)
        res.record["decision"] = "published"
    return res


def _section_passed(views: Sequence[EngineView], check: str, period: str) -> bool:
    found = [c for v in views for c in v.checks if c.name == check and c.period_id == period]
    return bool(found) and all(c.passed for c in found)


def _total_debt(
    period: str, views: Sequence[EngineView], res: Mapping[tuple[str, str], Resolution]
) -> Resolution:
    out = Resolution("total_debt", period)

    def found(item: str) -> bool:
        return any((m := v.mapped.get(item)) and (m.row or m.weak) for v in views)

    def got(item: str) -> Resolution:
        return res[(item, period)]

    fin, bor, lease = (
        found("financial_liabilities_current") or found("financial_liabilities_non_current"),
        found("borrowings_current") or found("borrowings_non_current"),
        found("lease_liabilities_current") or found("lease_liabilities_non_current"),
    )
    page = next(
        (
            r.cell.page
            for k, r in res.items()
            if k[1] == period and r.cell and k[0].startswith("financial_liabilities")
        ),
        None,
    )
    out.record["components_found"] = {
        "borrowings": bor,
        "leases": lease,
        "financial_liabilities": fin,
    }
    if fin and not bor:
        out.warn(
            "missing_item",
            "total_debt is null: the balance sheet face shows only 'Financial liabilities', which "
            "includes derivatives and other financial liabilities, so interest-bearing "
            "borrowings cannot be isolated "
            "from the face (CLAUDE.md: borrowings + leases). Debt-to-equity is therefore null.",
            page,
        )
        out.record["decision"] = "financial_liabilities_not_isolable"
        return out
    parts: list[tuple[str, Resolution | None]] = []
    blocked: list[str] = []
    for comp in DEBT_PARTS:
        if found(comp):
            r = got(comp)
            if r.value is None:
                blocked.append(f"{comp} is on the face but unresolved")
            parts.append((comp, r))
        elif comp.startswith("lease") and bor and not lease:
            continue  # borrowings resolved, leases not separately presented (warned below)
        elif _section_passed(views, _SECTION_CHECK[comp], period):
            parts.append((comp, None))  # absent, and the section subtotal proves every row was seen
        else:
            blocked.append(f"{comp} is absent and its section sum could not be verified")
    if blocked:
        out.warn("missing_item", "total_debt is null: " + "; ".join(blocked), page)
        out.record["decision"] = "blocked"
        return out
    total = sum(
        (Decimal(str(r.value)) for _, r in parts if r is not None and r.value is not None),
        Decimal(0),
    )
    out.value = float(total)
    out.engine, out.method = "derived", "derived"
    out.derived_from = [
        {"item": c, "period_id": period, **({"assumed_zero": True} if r is None else {})}
        for c, r in parts
    ]
    out.confidence = min([r.confidence for _, r in parts if r is not None] or [0.90])
    out.record["decision"] = "published_derived"
    out.warn("derived_value", f"total_debt is the sum of {[c for c, _ in parts]} ({period})")
    if bor and not lease:
        out.warn(
            "lease_not_separately_presented",
            "lease liabilities are not separately presented on the face; "
            "total_debt is borrowings only",
        )
    return out


def assemble(
    views: Sequence[EngineView],
    *,
    specs: Mapping[str, AliasSpec],
    located: LocateResult,
    header: Any,
    source: Mapping[str, Any],
    extra_warnings: Sequence[Mapping[str, Any]] = (),
) -> Assembly:
    """Build the pack and report from engine views whose tables carry period columns (M2.3)."""
    for view in views:
        for kind, table in view.tables.items():
            view.mapped.update(map_table(table, specs))
            view.checks.extend(
                run_checks(
                    table, {k: v for k, v in view.mapped.items() if specs[k].statement is kind}
                )
            )
    page_labels = {
        p: lab
        for loc in located.statements.values()
        for p, lab in zip(loc.pages, loc.page_labels, strict=True)
        if lab
    }
    statement_periods: dict[StatementType, list[str]] = {}
    for view in views:
        for kind, table in view.tables.items():
            for period in period_columns(table):
                statement_periods.setdefault(kind, [])
                if period not in statement_periods[kind]:
                    statement_periods[kind].append(period)

    res: dict[tuple[str, str], Resolution] = {}
    for item, spec in specs.items():
        for period in statement_periods.get(spec.statement, []):
            res[(item, period)] = _resolve(item, period, views, spec.statement)
    balance_periods = statement_periods.get(StatementType.BALANCE_SHEET, [])
    for period in balance_periods:
        res[("total_debt", period)] = _total_debt(period, views, res)
        ta = res.get(("total_assets", period))
        parts = [res.get(("non_current_assets", period)), res.get(("current_assets", period))]
        if (
            ta is not None
            and ta.record.get("decision") == "no_candidate"
            and all(p and p.value is not None for p in parts)
        ):
            ta.value = float(sum(Decimal(str(p.value)) for p in parts if p))
            ta.engine = ta.method = "derived"
            ta.derived_from = [
                {"item": i, "period_id": period} for i in ("non_current_assets", "current_assets")
            ]
            ta.confidence = min(p.confidence for p in parts if p)
            ta.record["decision"] = "published_derived"
            ta.warn(
                "derived_value", f"total_assets is non-current assets + current assets ({period})"
            )

    items: dict[str, Any] = {}
    warnings: list[dict[str, Any]] = [dict(w) for w in extra_warnings]
    order = [*specs, "total_debt"]
    for item in order:
        if item != "total_debt" and specs[item].internal:
            continue
        kind = specs[item].statement if item != "total_debt" else StatementType.BALANCE_SHEET
        periods = statement_periods.get(kind, [])
        rows = [res[(item, p)] for p in periods if (item, p) in res]
        if not rows or not (
            item in REQUIRED or any(r.record.get("decision") != "no_candidate" for r in rows)
        ):
            if item in REQUIRED and not rows:
                warnings.append(
                    {
                        "code": "missing_item",
                        "message": f"{item}: its statement was not located or has no usable period",
                        "item": item,
                        "page": None,
                    }
                )
            continue
        values = []
        for r in rows:
            entry: dict[str, Any] = {
                "period_id": r.period_id,
                "value": r.value,
                "confidence": r.confidence if r.value is not None else 0.0,
            }
            if r.cell is not None:
                entry.update(
                    page=r.cell.page,
                    raw_text=r.cell.raw_text,
                    bbox=list(r.cell.ink),
                    page_label=page_labels.get(r.cell.page),
                )
            entry["engine"] = r.engine
            if r.derived_from:
                entry.update(
                    derived_from=r.derived_from, derivation="sum", page=None, raw_text=None
                )
            if r.value is None:
                entry["engine"] = None
            values.append(entry)
            warnings.extend(r.warnings)
            if (
                r.value is None
                and item in REQUIRED
                and r.record.get("decision") in ("no_candidate", None)
            ):
                warnings.append(
                    {
                        "code": "missing_item",
                        "message": f"{item} not found for {r.period_id} on the "
                        f"{STATEMENT_OF[kind].replace('_', ' ')}",
                        "item": item,
                        "page": None,
                    }
                )
        first = next((r for r in rows if r.row is not None), None)
        items[item] = {
            "id": item,
            "label_found": (first.row.label_text or None) if first and first.row else None,
            "statement": STATEMENT_OF[kind],
            "note_ref": first.row.note_ref if first and first.row else None,
            "values": values,
        }
    for item in REQUIRED:
        if item in items:
            continue
        kind = specs[item].statement if item in specs else StatementType.BALANCE_SHEET
        periods = statement_periods.get(kind) or [p.id for p in header.periods]
        kind_name = located.profile.document_type.value
        reason = f"not extracted: no alias map for document type {kind_name} yet"
        items[item] = {
            "id": item, "label_found": None, "statement": STATEMENT_OF[kind], "note_ref": None,
            "values": [{"period_id": p, "value": None, "confidence": 0.0} for p in periods],
        }  # fmt: skip
        warnings.append(
            {"code": "missing_item", "message": f"{item} {reason}", "item": item, "page": None}
        )
    pack: dict[str, Any] = {
        "schema_version": "1.1.0",
        "company_name": None,
        "document_type": located.profile.document_type.value,
        "basis": _basis(located),
        "source": {
            **source,
            "parser_engines": [v.engine for v in views],
            "pipeline_version": PIPELINE_VERSION,
        },
        "currency": header.currency,
        "unit_scale": header.unit_scale,
        "periods": [
            {
                "id": p.id,
                "label": p.label,
                "end_date": p.end_date,
                "is_restated": p.is_restated,
                **({"weeks": p.weeks} if p.weeks else {}),
            }
            for p in header.periods
        ],
        "items": items,
        "warnings": _dedupe(warnings),
    }
    if located.profile.balance_sheet_classified is not None:
        pack["balance_sheet_classified"] = located.profile.balance_sheet_classified
    report = {
        "engines": [v.engine for v in views],
        "tau": TAU,
        "candidates": {f"{i}:{p}": r.record for (i, p), r in sorted(res.items())},
        "checks": [
            {
                "engine": v.engine,
                "name": c.name,
                "period": c.period_id,
                "passed": c.passed,
                "difference": str(c.difference),
                "tolerance": str(c.tolerance),
                "detail": c.detail,
            }
            for v in views
            for c in v.checks
        ],
        "table_notes": {
            f"{v.engine}:{k.value}": list(t.notes) for v in views for k, t in v.tables.items()
        },
    }
    return Assembly(pack, report)


def _basis(located: LocateResult) -> str:
    scope = located.statements[StatementType.BALANCE_SHEET].scope
    if scope is None:
        return "consolidated"
    return {"single_entity": "single_entity", "company": "company_only"}.get(
        scope.value, "consolidated"
    )


def _dedupe(warnings: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    seen, out = set(), []
    for w in warnings:
        key = (w["code"], w.get("item"), w["message"])
        if key not in seen:
            seen.add(key)
            out.append(
                {
                    "code": w["code"],
                    "message": w["message"],
                    "item": w.get("item"),
                    "page": w.get("page"),
                }
            )
    return out
