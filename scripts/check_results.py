"""M8.3 gate: every number in docs/RESULTS.md equals a field of the eval report it cites.

    python scripts/check_results.py                 # check docs/RESULTS.md
    python scripts/check_results.py --snapshot      # copy artifacts/eval/latest/report.json to
                                                    # docs/results/{run_id}.json (once per run)

A line that states a number cites its run and fields at the end, for example

    | E1 matched | 22 of 22 | `company_a-20261003T101500Z-4ea9338`: e1.matched, e1.labelled |

The checker reads docs/results/{run_id}.json (committed snapshots of artifacts/eval/{run_id}/
report.json, so a fresh clone can check them), and every number on the line outside the citation
must equal one of the cited fields' values. A line with a number and no citation fails; so does a
cited field that the report does not have. Names that contain digits are not numbers: milestone
and suite names (M8.3, E1, QA-20, T17, OQ-4), hit@8, company ids, run ids, dates and code spans.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "docs" / "RESULTS.md"
SNAPSHOTS = ROOT / "docs" / "results"
LATEST = ROOT / "artifacts" / "eval" / "latest" / "report.json"

_CITATION = re.compile(r"`(?P<run>[a-z0-9_]+-\d{8}T\d{6}Z-[0-9a-z]+)`:\s*(?P<fields>[\w.\[\], ]+)")
_NAMES = re.compile(
    r"`[^`]*`|\b(?:M|E|T|OQ-|QA-|ADR-|R|K|V|G)\d+(?:\.\d+)?\b|@\d+|\bcompany_[a-z]\b|"
    r"\b\d{4}-\d{2}-\d{2}\b|\bFY\d{4}\b|\[[^\]]*\]\([^)]*\)"
)
_NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?(?:e-?\d+)?(?![\w.]?\d)")


def _value(report: Any, path: str) -> Any:
    node = report
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            raise KeyError(path)
    return node


def _numbers(text: str) -> list[float]:
    cleaned = _NAMES.sub(" ", text)
    return [float(n.replace(",", "")) for n in _NUMBER.findall(cleaned)]


def check(results: Path = RESULTS, snapshots: Path = SNAPSHOTS) -> list[str]:
    """Problems found; empty when every number is backed by a cited report field."""
    problems: list[str] = []
    if not results.is_file():
        return [f"{results} is missing"]
    in_code = False
    for n, line in enumerate(results.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or line.lstrip().startswith("#"):
            continue
        citations = list(_CITATION.finditer(line))
        body = _CITATION.sub(" ", line)
        numbers = _numbers(body)
        if not numbers:
            continue
        if not citations:
            problems.append(f"line {n}: numbers {numbers} with no cited run: {line.strip()[:90]}")
            continue
        allowed: list[float] = []
        for c in citations:
            path = snapshots / f"{c.group('run')}.json"
            if not path.is_file():
                problems.append(f"line {n}: cited run {c.group('run')} has no snapshot {path}")
                continue
            report = json.loads(path.read_text(encoding="utf-8"))
            for field in (f.strip() for f in c.group("fields").split(",") if f.strip()):
                try:
                    value = _value(report, field)
                except KeyError:
                    problems.append(f"line {n}: {c.group('run')} has no field {field}")
                    continue
                if isinstance(value, bool) or not isinstance(value, int | float):
                    problems.append(f"line {n}: {field} is not a number ({value!r})")
                    continue
                allowed.append(float(value))
        for number in numbers:
            if not any(abs(number - a) <= 1e-12 * max(1.0, abs(a)) for a in allowed):
                problems.append(f"line {n}: {number:g} is not one of the cited fields {allowed}")
    return problems


def snapshot(latest: Path = LATEST, snapshots: Path = SNAPSHOTS) -> Path:
    report = json.loads(latest.read_text(encoding="utf-8"))
    run = report.get("run_id")
    if not run:
        raise SystemExit(f"{latest} has no run_id: run make eval first")
    target = snapshots / f"{run}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(latest, target)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--snapshot", action="store_true")
    args = parser.parse_args(argv)
    if args.snapshot:
        print(f"wrote {snapshot().relative_to(ROOT)}")
        return 0
    problems = check()
    for p in problems:
        print(f"FAIL  {p}")
    if not problems:
        print("PASS  every number in docs/RESULTS.md equals a field of the report it cites")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
