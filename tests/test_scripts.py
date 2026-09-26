"""Gate tooling: scope, imports, eval-report conditions and contract drift."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import check_imports, check_scope, gate, gen_contracts, gen_scope

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_SESSIONS = [
    "M0", "M1", "M2.1", "M2.2", "M2.3", "M2.4", "M2.5", "M3", "M4.1", "M4.2",
    "M5.1", "M5.2", "M6.1", "M6.2", "M7.1", "M7.2", "M7.3", "M8.1", "M8.3",
]  # fmt: skip
OPTIONAL_SESSIONS = ["M2.6", "M8.2"]


@pytest.mark.parametrize(
    ("path", "glob", "expected"),
    [
        ("finintel/locate/pages.py", "finintel/locate/**", True),
        ("finintel/locate/sub/deep.py", "finintel/locate/**", True),
        ("finintel/locater.py", "finintel/locate/**", False),
        ("finintel/parse/engines/pdfplumber_engine.py", "finintel/parse/engines/pdfplumber*", True),
        ("finintel/parse/engines/azure_di_engine.py", "finintel/parse/engines/pdfplumber*", False),
        ("tests/golden/company_a/page_142.json", "tests/**", True),
        ("CLAUDE.md", "CLAUDE.md", True),
        ("docs/CLAUDE.md", "CLAUDE.md", False),
    ],
)
def test_glob_matching(path: str, glob: str, expected: bool) -> None:
    assert check_scope.matches(path, [glob]) is expected


def test_scope_file_is_in_sync_with_milestones() -> None:
    assert gen_scope.main(["--check"]) == 0


def test_every_session_has_allowed_paths() -> None:
    _, sessions = check_scope.load_scope()
    assert sorted(sessions) == sorted(REQUIRED_SESSIONS + OPTIONAL_SESSIONS)
    assert all(sessions[s] for s in sessions)


def test_global_allow_list_covers_milestones_and_dependencies() -> None:
    global_allowed, _ = check_scope.load_scope()
    for path in ("docs/MILESTONES.md", "pyproject.toml", "uv.lock", "tests/foo.py"):
        assert check_scope.matches(path, global_allowed)


def test_scope_violations(monkeypatch: pytest.MonkeyPatch) -> None:
    changed = {
        "finintel/locate/pages.py",
        "docs/MILESTONES.md",
        "finintel/ratios/core.py",
        "fixtures/expected/company_a.json",
        "CLAUDE.md",
    }
    problems = check_scope.violations(changed, "M2.1")
    assert any("G2" in p and "finintel/ratios/core.py" in p for p in problems)
    assert any(p.startswith("G3") for p in problems)
    assert any(p.startswith("G4") for p in problems)
    assert not any("finintel/locate/pages.py" in p for p in problems)


def test_forbidden_import_is_detected(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "ok.py").write_text("import json\nfrom pathlib import Path\n")
    (pkg / "bad.py").write_text("import fitz\nfrom anthropic import Anthropic\n")
    hits = check_imports.find_forbidden(pkg, {"fitz", "anthropic", "httpx"})
    assert hits == ["pkg/bad.py imports anthropic", "pkg/bad.py imports fitz"]


# Which modules may import which libraries. A new owner is added in the session that needs it.
IMPORT_OWNERS = {
    "pymupdf": ("finintel/parse/", "finintel/ingest/"),
    "fitz": (),  # the legacy PyMuPDF name: use `import pymupdf`
    "pdfplumber": ("finintel/parse/engines/pdfplumber_engine.py",),
    "httpx": ("finintel/parse/engines/azure_di_engine.py",),
    "anthropic": (),  # LLM calls arrive in M2.4 (finintel/llm/)
    "voyageai": (),  # embeddings arrive in M4.2 (finintel/retrieval/)
}


@pytest.mark.parametrize(("module", "owners"), IMPORT_OWNERS.items())
def test_stage_import_boundaries(module: str, owners: tuple[str, ...]) -> None:
    hits = check_imports.find_forbidden(ROOT / "finintel", {module})
    strays = [hit for hit in hits if not hit.startswith(owners)] if owners else hits
    assert strays == []


def test_gate_conditions(tmp_path: Path) -> None:
    report = {"e1": {"labelled": 14, "matched": 14, "honest_null": 0, "silent_wrong": 0,
                     "unit_errors": 0}, "e6": {"published_llm_pointer": 0}}  # fmt: skip
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    assert gate.run("M2.4", path)[0] == 0
    report["e6"]["published_llm_pointer"] = 1
    path.write_text(json.dumps(report))
    code, lines = gate.run("M2.4", path)
    assert code == 1
    assert "FAIL  e6.published_llm_pointer == 0" in lines


def test_gate_missing_report_fails(tmp_path: Path) -> None:
    assert gate.run("M3", tmp_path / "absent.json")[0] == 1


def test_gate_pending_and_command_only_sessions(tmp_path: Path) -> None:
    assert gate.run("M2.1", tmp_path / "absent.json")[0] == 2
    assert gate.run("M0", tmp_path / "absent.json")[0] == 0


def test_gate_evaluates_sums() -> None:
    report = {"e1": {"matched": 10, "honest_null": 2, "labelled": 12}}
    assert gate.evaluate("e1.matched + e1.honest_null == e1.labelled", report)


def test_generated_contracts_are_up_to_date() -> None:
    assert gen_contracts.main(["--check"]) == 0
