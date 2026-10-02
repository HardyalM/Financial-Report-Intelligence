"""Gate tooling: scope, imports, eval-report conditions and contract drift."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
    "httpx": (
        "finintel/parse/engines/azure_di_engine.py",
        "finintel/llm/anthropic_provider.py",
        "finintel/llm/openai_compat.py",
    ),
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


def test_gate_pending_and_command_only_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gate, "PENDING", {"M0"})
    assert gate.run("M0", tmp_path / "absent.json")[0] == 2
    monkeypatch.undo()
    assert gate.run("M0", tmp_path / "absent.json")[0] == 0


def test_gate_evaluates_sums() -> None:
    report = {"e1": {"matched": 10, "honest_null": 2, "labelled": 12}}
    assert gate.evaluate("e1.matched + e1.honest_null == e1.labelled", report)


def test_generated_contracts_are_up_to_date() -> None:
    assert gen_contracts.main(["--check"]) == 0


def _located(pages: dict[str, tuple[int, ...]], kind: str, classified: bool, company: bool) -> Any:
    from finintel.locate import (
        DocumentProfile,
        DocumentType,
        LocateResult,
        PageCandidate,
        Scope,
        StatementLocation,
        StatementType,
    )

    statements = {
        StatementType(k): StatementLocation(
            statement_type=StatementType(k), status="found", pages=v
        )
        for k, v in pages.items()
    }
    candidates: tuple[PageCandidate, ...] = ()
    if company:
        candidates = (
            PageCandidate(
                page=197,
                page_label=None,
                statement_type=StatementType.BALANCE_SHEET,
                title="Balance sheet",
                scope=Scope.COMPANY,
                scope_evidence="header",
                score=1.0,
                signals=(),
                excluded="company-only",
            ),
        )
    profile = DocumentProfile(
        document_type=DocumentType(kind), balance_sheet_classified=classified, evidence={}
    )
    return LocateResult(
        locator_version="1",
        page_count=305,
        folio_offset=3,
        statements=statements,
        candidates=candidates,
        profile=profile,
        warnings=(),
    )


def test_gate_m2_1_compares_located_pages_with_labels() -> None:
    labels = {"items": {
        "revenue": {"statement": "income_statement", "values": [{"page": 141}, {"page": 141}]},
        "total_assets": {"statement": "balance_sheet", "values": [{"page": 143}]},
        "total_debt": {"statement": "balance_sheet", "values": [{"page": None}]},
    }}  # fmt: skip
    good = {
        "company_a": _located(
            {"income_statement": (141,), "balance_sheet": (143,)}, "corporate", True, True
        ),
        "company_b": _located(
            {"income_statement": (216,), "balance_sheet": (218,)}, "bank", False, True
        ),
    }
    assert all(ok for ok, _ in gate.check_m21(good, labels))

    wrong_page = {
        **good,
        "company_a": _located(
            {"income_statement": (141,), "balance_sheet": (197,)}, "corporate", True, True
        ),
    }
    failed = [text for ok, text in gate.check_m21(wrong_page, labels) if not ok]
    assert failed == ["company_a balance_sheet: located [197] (found), labelled [143]"]

    no_company = {
        **good,
        "company_a": _located(
            {"income_statement": (141,), "balance_sheet": (143,)}, "corporate", True, False
        ),
    }
    assert [ok for ok, text in gate.check_m21(no_company, labels) if "scope=company" in text] == [
        False
    ]


def test_gate_m2_2_requires_every_labelled_cell_per_engine() -> None:
    from decimal import Decimal

    from finintel.locate import StatementType
    from finintel.parse.engines.base import EngineFamily
    from finintel.tables import Cell, Column, ColumnKind, Row, RowStyle, StatementTable

    def table(engine: str, text: str) -> StatementTable:
        box = (0.0, 0.0, 1.0, 1.0)
        cell = Cell(
            raw_text=text, engine_text=text, parsed_value=Decimal(0), bbox=box, ink=box, page=141
        )
        row = Row(
            row_id="141:1", label_text="Turnover", note_ref=None, section_header=None, sections=(),
            indent_level=0, style=RowStyle.NORMAL, page=141, bbox=box, cells={"v1": cell},
        )  # fmt: skip
        column = Column(
            column_id="v1", kind=ColumnKind.VALUE, header_text="2024", x0=0, x1=1, evidence=""
        )
        return StatementTable(
            statement_type=StatementType.INCOME_STATEMENT,
            scope=None,
            engine=engine,
            engine_version="1",
            family=EngineFamily.TEXT_LAYER,
            pages=(141,),
            strategies={141: "text"},
            columns=(column,),
            rows=(row,),
        )

    labels = {"items": {"revenue": {"statement": "income_statement", "values": [
        {"period_id": "FY2024", "page": 141, "raw_text": "60,761"},
        {"period_id": "FY2023", "page": 141, "raw_text": None},
    ]}}}  # fmt: skip
    good = {StatementType.INCOME_STATEMENT: {e: table(e, "60761") for e in gate.TEXT_LAYER_ENGINES}}
    assert all(ok for ok, _ in gate.check_m22(good, labels))
    short = {
        "pdfplumber": table("pdfplumber", "60,761"),
        "pymupdf_tables": table("pymupdf_tables", "60,716"),
    }
    one_short = {StatementType.INCOME_STATEMENT: short}
    results = gate.check_m22(one_short, labels)
    assert [ok for ok, _ in results] == [True, False]
    assert "missing: revenue FY2024 '60,761' p.141" in results[1][1]


def test_the_m81_gate_reads_company_b_and_checks_ratios_and_absent_items(tmp_path: Path) -> None:
    from scripts import gate

    report = {
        "company": "company_b",
        "e1": {"labelled": 28, "matched": 28, "honest_null": 0, "silent_wrong": 0},
        "ratios": {"not_applicable": 4, "computed": 0},
        "absent": {"published": 0},
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    assert gate.run("M8.1", path)[0] == 0
    for change in (
        {"company": "company_a"},
        {"ratios": {"not_applicable": 3, "computed": 0}},
        {"ratios": {"not_applicable": 4, "computed": 1}},
        {"absent": {"published": 1}},
    ):
        path.write_text(json.dumps({**report, **change}))
        assert gate.run("M8.1", path)[0] == 1, change
