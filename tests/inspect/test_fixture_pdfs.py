"""The inspector on the real fixture PDFs (M1 gate). PDFs are git-ignored, so CI skips this.

When `fixtures/expected/{stem}.json` exists (never an EXAMPLE file), the dump's page count must
equal the label's `source.page_count`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from finintel.cli.inspect import InspectOptions, inspect_pdf

ROOT = Path(__file__).resolve().parents[2]
PDFS = sorted((ROOT / "fixtures" / "pdfs").glob("*.pdf"))


@pytest.mark.skipif(
    not PDFS, reason="no PDFs in fixtures/pdfs/ yet: blocked on the tech lead (PLAN section 7.1)"
)
@pytest.mark.parametrize("pdf", PDFS, ids=[p.stem for p in PDFS])
def test_inspector_runs_on_fixture(pdf: Path, tmp_path: Path) -> None:
    options = InspectOptions(
        out_dir=tmp_path / "inspect",
        cache_dir=ROOT / "artifacts" / "cache",  # content-addressed: safe to share
        azure=None,
    )
    result = inspect_pdf(pdf, options)
    summary = result.summary
    assert summary["page_count"] >= 1
    assert (result.dump_dir / "pages.jsonl").read_text().count("\n") == summary["page_count"]

    expected = ROOT / "fixtures" / "expected" / f"{pdf.stem}.json"
    if expected.exists():
        labelled = json.loads(expected.read_text(encoding="utf-8"))
        assert summary["page_count"] == labelled["source"]["page_count"]
