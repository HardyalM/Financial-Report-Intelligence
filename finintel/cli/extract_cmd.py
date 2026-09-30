"""`finintel extract` and `finintel eval-e1` (M2.4).

    finintel extract company_a [--json]         pack + warnings; writes artifacts/extract/{stem}/
    finintel eval-e1 company_a --engines local  E1 against fixtures/expected; writes
                                                artifacts/eval/latest/report.json
Exit codes: 0 ok; 1 blocked, refused or failed a gate condition; 2 usage; 3 held-out path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TextIO

from finintel.cache import StageCache
from finintel.cli.common import resolve_pdf
from finintel.evals.e1 import compare, report_json, write_report
from finintel.extract import ExtractionResult, extract_pack


def run_extract(
    target: str, cache_dir: Path, artifacts: Path, engines: str
) -> tuple[Path, ExtractionResult, Path]:
    pdf = resolve_pdf(target)
    result = extract_pack(pdf, StageCache(cache_dir), engines=engines)
    out = artifacts / "extract" / pdf.stem
    out.mkdir(parents=True, exist_ok=True)
    if result.pack is not None:
        (out / "pack.json").write_text(json.dumps(result.pack, indent=2) + "\n", encoding="utf-8")
    (out / "report.json").write_text(
        json.dumps({"status": result.status, **result.report}, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return pdf, result, out


def _fmt(v: dict[str, Any]) -> str:
    return f"{v['period_id']}=" + ("null" if v["value"] is None else f"{v['value']:,.10g}")


def print_summary(pdf: Path, result: ExtractionResult, out: Path, stream: TextIO) -> None:
    print(f"{pdf.name}  status={result.status}", file=stream)
    if result.pack is None:
        for w in result.warnings:
            print(f"  warning {w['code']}: {w['message']}", file=stream)
        return
    pack = result.pack
    print(
        f"  {pack['currency']} x {pack['unit_scale']:,}  "
        f"periods {[p['id'] for p in pack['periods']]}",
        file=stream,
    )
    for item, body in pack["items"].items():
        shown = "  ".join(_fmt(v) for v in body["values"])
        print(f"  {item:34} {shown}", file=stream)
    for w in pack["warnings"]:
        print(
            f"  warning {w['code']}{' (' + w['item'] + ')' if w['item'] else ''}: {w['message']}",
            file=stream,
        )
    if result.schema_errors:
        print(f"  SCHEMA ERRORS: {result.schema_errors}", file=stream)
    print(f"  -> {out}", file=stream)


def run_e1(
    company: str, engines: str, cache_dir: Path, artifacts: Path
) -> tuple[dict[str, Any], Path]:
    pdf = resolve_pdf(company)
    expected_path = Path("fixtures") / "expected" / f"{pdf.stem}.json"
    if not expected_path.is_file():
        raise FileNotFoundError(
            f"{expected_path} is missing: labels are the tech lead's (PLAN section 7)"
        )
    if pdf.stem.upper().startswith("EXAMPLE"):
        raise ValueError("EXAMPLE files are dummy data, not labels")
    result = extract_pack(pdf, StageCache(cache_dir), engines=engines)
    if result.pack is None:
        raise RuntimeError(
            f"extraction blocked: {result.status}: {[w['message'] for w in result.warnings]}"
        )
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    e1 = compare(result.pack, expected, result.report)
    report = report_json(e1, pdf.stem, engines, {"schema_errors": result.schema_errors})
    path = write_report(report, artifacts / "eval" / "latest" / "report.json")
    return report, path
