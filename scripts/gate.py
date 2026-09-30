"""Session gates that read the eval report (docs/MILESTONES.md, "Eval report contract").

    python scripts/gate.py M2.4 [--report artifacts/eval/latest/report.json]
    python scripts/gate.py M2.1                      # runs the locator on the fixture PDFs
    python scripts/gate.py M2.2                      # builds StatementTables for company_a
    python scripts/gate.py M2.3                      # reads company_a's units and periods

Exit codes: 0 = all conditions hold; 1 = a condition fails or the report is missing;
2 = this session's scripted check is not implemented yet (it is added in that session).
Sessions whose gates are commands and sign-offs only exit 0 with a note.
"""

from __future__ import annotations

import argparse
import ast
import json
import operator
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from finintel.locate import LocateResult, StatementType
    from finintel.tables import StatementTable
    from finintel.tables.headers import HeaderResult

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT = ROOT / "artifacts" / "eval" / "latest" / "report.json"

CONDITIONS: dict[str, list[str]] = {
    "M2.4": [
        "e1.matched == e1.labelled",
        "e1.silent_wrong == 0",
        "e1.unit_errors == 0",
        "e6.published_llm_pointer == 0",
    ],
    "M2.5": ["azure.ran == True", "e1.matched == e1.labelled", "e1.silent_wrong == 0"],
    "M2.6": ["e6.published_vision_only == 0"],
    "M3": ["e2.matched == e2.expected"],
    "M4.2": ["e3.hit_at_8 >= 0.8"],
    "M5.2": [
        "e4.displayed_unverified_citations == 0",
        "e4.displayed_naked_numbers == 0",
        "e4.displayed_advice == 0",
        "e8.risk_recall >= 0.8",
        "e8.kam_recall >= 0.8",
        "e8.going_concern_correct == True",
        "qa.total == 20",
        "qa.passed >= 17",
    ],
    "M8.1": ["e1.matched + e1.honest_null == e1.labelled", "e1.silent_wrong == 0"],
}
# Scripted checks that compare pipeline output with labels; each is written in its own session.
PENDING = {"M4.1", "M8.1"}

_COMPARE = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.GtE: operator.ge,
    ast.Gt: operator.gt,
    ast.LtE: operator.le,
    ast.Lt: operator.lt,
}


def evaluate(expression: str, report: dict[str, Any]) -> bool:
    """Evaluate a condition such as "e1.matched + e1.honest_null == e1.labelled" safely."""

    def value(node: ast.expr) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            return report[node.value.id][node.attr]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return value(node.left) + value(node.right)
        raise ValueError(f"unsupported expression: {ast.dump(node)}")

    tree = ast.parse(expression, mode="eval").body
    if not isinstance(tree, ast.Compare) or len(tree.ops) != 1:
        raise ValueError(f"not a single comparison: {expression}")
    return bool(_COMPARE[type(tree.ops[0])](value(tree.left), value(tree.comparators[0])))


def check_m21(
    results: Mapping[str, LocateResult], labels: Mapping[str, Any]
) -> list[tuple[bool, str]]:
    """M2.1: statement pages equal the labelled pages; company pages seen and rejected; profiles."""
    from finintel.locate import DocumentType, Scope, StatementType

    checks: list[tuple[bool, str]] = []
    a, b = results["company_a"], results["company_b"]
    for kind in (StatementType.INCOME_STATEMENT, StatementType.BALANCE_SHEET):
        labelled = sorted(
            {
                v["page"]
                for item in labels["items"].values()
                if item.get("statement") == kind.value
                for v in item["values"]
                if v.get("page") is not None
            }
        )
        location = a.statements[kind]
        ok = location.status == "found" and sorted(location.pages) == labelled
        located = f"located {list(location.pages)} ({location.status})"
        checks.append((ok, f"company_a {kind.value}: {located}, labelled {labelled}"))
    company = sorted({c.page for c in a.candidates if c.scope is Scope.COMPANY})
    selected = any(c.selected for c in a.candidates if c.scope is Scope.COMPANY)
    checks.append(
        (
            bool(company) and not selected,
            f"company_a scope=company pages {company} detected, none selected",
        )
    )
    checks.append(
        (
            a.profile.document_type is DocumentType.CORPORATE,
            f"company_a document_type == corporate ({a.profile.document_type.value})",
        )
    )
    checks.append(
        (
            a.profile.balance_sheet_classified is True,
            f"company_a balance_sheet_classified == true ({a.profile.balance_sheet_classified})",
        )
    )
    checks.append(
        (
            b.profile.document_type is DocumentType.BANK,
            f"company_b document_type == bank ({b.profile.document_type.value})",
        )
    )
    checks.append(
        (
            b.profile.balance_sheet_classified is False,
            f"company_b balance_sheet_classified == false ({b.profile.balance_sheet_classified})",
        )
    )
    return checks


def gate_m21() -> tuple[int, list[str]]:
    from finintel.cache import StageCache
    from finintel.cli.common import cached_text_layer
    from finintel.ingest import sha256_file
    from finintel.locate import locate

    results = {}
    for name in ("company_a", "company_b"):
        pdf = ROOT / "fixtures" / "pdfs" / f"{name}.pdf"
        if not pdf.exists():
            return 1, [f"FAIL  {pdf.relative_to(ROOT)} is missing (PLAN section 7.1)"]
        layer, _ = cached_text_layer(
            pdf, sha256_file(pdf), StageCache(ROOT / "artifacts" / "cache")
        )
        results[name] = locate(layer)
    labels = json.loads(
        (ROOT / "fixtures" / "expected" / "company_a.json").read_text(encoding="utf-8")
    )
    checks = check_m21(results, labels)
    lines = [f"{'PASS' if ok else 'FAIL'}  {text}" for ok, text in checks]
    return (0 if all(ok for ok, _ in checks) else 1), lines


TEXT_LAYER_ENGINES = ("pdfplumber", "pymupdf_tables")


def check_m22(
    tables: Mapping[StatementType, Mapping[str, StatementTable]], labels: Mapping[str, Any]
) -> list[tuple[bool, str]]:
    """M2.2: every labelled cell exists, per engine, on its labelled page in a value column with
    the same printed text (canonical comparison, EVAL section 3.1)."""
    from finintel.locate import StatementType
    from finintel.tables import ColumnKind, canonical

    cells = [
        (item_id, item, v)
        for item_id, item in labels["items"].items()
        for v in item["values"]
        if v.get("raw_text")
    ]
    checks: list[tuple[bool, str]] = []
    for engine in TEXT_LAYER_ENGINES:
        missing = []
        for item_id, item, v in cells:
            table = tables.get(StatementType(item["statement"]), {}).get(engine)
            values = (
                {c.column_id for c in table.columns if c.kind is ColumnKind.VALUE}
                if table
                else set()
            )
            found = table is not None and any(
                cell.page == v["page"]
                and cid in values
                and canonical(cell.raw_text) == canonical(v["raw_text"])
                for row in table.rows
                for cid, cell in row.cells.items()
            )
            if not found:
                missing.append(f"{item_id} {v['period_id']} {v['raw_text']!r} p.{v['page']}")
        found_n = len(cells) - len(missing)
        detail = f"; missing: {', '.join(missing)}" if missing else ""
        checks.append(
            (
                not missing,
                f"{engine}: {found_n}/{len(cells)} labelled cells in a value column on their "
                f"page{detail}",
            )
        )
    return checks


def gate_m22() -> tuple[int, list[str]]:
    from finintel.cache import StageCache
    from finintel.cli.common import cached_text_layer
    from finintel.ingest import sha256_file
    from finintel.locate import locate
    from finintel.tables import statement_tables

    pdf = ROOT / "fixtures" / "pdfs" / "company_a.pdf"
    labels_path = ROOT / "fixtures" / "expected" / "company_a.json"
    if not pdf.exists() or not labels_path.exists():
        return 1, [
            "FAIL  fixtures/pdfs/company_a.pdf and fixtures/expected/company_a.json are required"
        ]
    cache = StageCache(ROOT / "artifacts" / "cache")
    sha = sha256_file(pdf)
    layer, _ = cached_text_layer(pdf, sha, cache)
    tables = statement_tables(pdf, sha, layer, locate(layer), cache)
    checks = check_m22(tables, json.loads(labels_path.read_text(encoding="utf-8")))
    lines = [f"{'PASS' if ok else 'FAIL'}  {text}" for ok, text in checks]
    return (0 if all(ok for ok, _ in checks) else 1), lines


def check_m23(
    results: Mapping[str, HeaderResult], labels: Mapping[str, Any]
) -> list[tuple[bool, str]]:
    """M2.3: unit scale, currency, period ids and end dates equal the labels, per engine."""
    checks: list[tuple[bool, str]] = []
    for engine, result in results.items():
        checks.append((result.status == "ok", f"{engine}: header status {result.status}"))
        checks.append(
            (
                (result.currency, result.unit_scale) == (labels["currency"], labels["unit_scale"]),
                f"{engine}: {result.currency} x {result.unit_scale}, labelled "
                f"{labels['currency']} x {labels['unit_scale']}",
            )
        )
        found = {p.id: p for p in result.periods}
        for period in labels["periods"]:
            got = found.get(period["id"])
            same = got is not None and got.end_date == period["end_date"]
            same = same and got is not None and got.is_restated == period.get("is_restated", False)
            seen = f"{got.end_date} restated={got.is_restated}" if got else "missing"
            checks.append(
                (same, f"{engine}: {period['id']} ends {period['end_date']} (read: {seen})")
            )
        extra = sorted(set(found) - {p["id"] for p in labels["periods"]})
        if extra:
            checks.append((True, f"{engine}: also printed, not labelled: {extra}"))
    return checks


def gate_m23() -> tuple[int, list[str]]:
    from finintel.cache import StageCache
    from finintel.cli.common import cached_text_layer
    from finintel.ingest import sha256_file
    from finintel.locate import locate
    from finintel.tables import statement_tables
    from finintel.tables.headers import read_headers

    pdf = ROOT / "fixtures" / "pdfs" / "company_a.pdf"
    labels_path = ROOT / "fixtures" / "expected" / "company_a.json"
    if not pdf.exists() or not labels_path.exists():
        return 1, [
            "FAIL  fixtures/pdfs/company_a.pdf and fixtures/expected/company_a.json are required"
        ]
    cache = StageCache(ROOT / "artifacts" / "cache")
    sha = sha256_file(pdf)
    layer, _ = cached_text_layer(pdf, sha, cache)
    tables = statement_tables(pdf, sha, layer, locate(layer), cache)
    results = {
        engine: read_headers({kind: by_engine[engine] for kind, by_engine in tables.items()}, layer)
        for engine in TEXT_LAYER_ENGINES
    }
    checks = check_m23(results, json.loads(labels_path.read_text(encoding="utf-8")))
    lines = [f"{'PASS' if ok else 'FAIL'}  {text}" for ok, text in checks]
    return (0 if all(ok for ok, _ in checks) else 1), lines


SCRIPTED: dict[str, Callable[[], tuple[int, list[str]]]] = {
    "M2.1": gate_m21,
    "M2.2": gate_m22,
    "M2.3": gate_m23,
}


def run(session: str, report_path: Path) -> tuple[int, list[str]]:
    if session in SCRIPTED:
        return SCRIPTED[session]()
    lines: list[str] = []
    conditions = CONDITIONS.get(session, [])
    if conditions:
        if not report_path.exists():
            return 1, [f"{session}: eval report not found at {report_path}"]
        report = json.loads(report_path.read_text(encoding="utf-8"))
        failed = False
        for condition in conditions:
            try:
                ok = evaluate(condition, report)
            except (KeyError, ValueError) as exc:
                ok, condition = False, f"{condition} (cannot evaluate: {exc})"
            failed |= not ok
            lines.append(f"{'PASS' if ok else 'FAIL'}  {condition}")
        if failed:
            return 1, lines
    if session in PENDING:
        return 2, [*lines, f"{session}: scripted comparison is added in {session} itself"]
    if not conditions:
        lines.append(f"{session}: no scripted conditions (gate is commands and sign-offs)")
    return 0, lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Eval-report gates")
    parser.add_argument("session")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)
    code, lines = run(args.session.upper(), args.report)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
