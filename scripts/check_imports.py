"""Fail if code under finintel/ imports a forbidden top-level module.

    python scripts/check_imports.py --forbid fitz,pdfplumber,httpx,anthropic,voyageai

Used by the M0 gate to prove no parsing or LLM code slipped in before its milestone.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def imported_modules(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def find_forbidden(package_dir: Path, forbidden: set[str]) -> list[str]:
    hits = []
    for path in sorted(package_dir.rglob("*.py")):
        bad = imported_modules(path.read_text(encoding="utf-8")) & forbidden
        hits += [f"{path.relative_to(package_dir.parent)} imports {name}" for name in sorted(bad)]
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--forbid", required=True, help="comma-separated top-level module names")
    parser.add_argument("--package", default="finintel")
    args = parser.parse_args(argv)
    forbidden = {name.strip() for name in args.forbid.split(",") if name.strip()}
    hits = find_forbidden(ROOT / args.package, forbidden)
    for hit in hits:
        print(hit)
    print("no forbidden imports" if not hits else f"{len(hits)} forbidden import(s)")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
