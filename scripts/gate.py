"""Session gates that read the eval report (docs/MILESTONES.md, "Eval report contract").

    python scripts/gate.py M2.4 [--report artifacts/eval/latest/report.json]

Exit codes: 0 = all conditions hold; 1 = a condition fails or the report is missing;
2 = this session's scripted check is not implemented yet (it is added in that session).
Sessions whose gates are commands and sign-offs only exit 0 with a note.
"""

from __future__ import annotations

import argparse
import ast
import json
import operator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT = ROOT / "artifacts" / "eval" / "latest" / "report.json"

CONDITIONS: dict[str, list[str]] = {
    "M2.4": [
        "e1.matched == e1.labelled",
        "e1.silent_wrong == 0",
        "e1.unit_errors == 0",
        "e6.published_llm_pointer == 0",
    ],
    "M2.5": ["e1.matched == e1.labelled", "e1.silent_wrong == 0"],
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
PENDING = {"M2.1", "M2.2", "M2.3", "M4.1", "M8.1"}

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


def run(session: str, report_path: Path) -> tuple[int, list[str]]:
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
