"""`finintel inspect` end to end on synthetic reports (M1 gate behaviour, offline)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from structlog.testing import capture_logs

from finintel.cli import main
from finintel.cli.inspect import InspectOptions, _table_candidates, inspect_pdf
from finintel.cli.page_signals import PageSignals
from finintel.parse.engines.azure_di_engine import AzureDiConfig, AzureDiEngine
from tests.inspect.synthetic import LOREM, encrypted_pdf, mini_report

KEY = "sk-test-SECRET-9d2e"
AZURE = AzureDiConfig(endpoint="https://example-di.cognitiveservices.azure.com", key=KEY)
BODY = {"status": "succeeded", "analyzeResult": {"pages": [{"pageNumber": n} for n in range(1, 8)]}}


def _run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = main(["inspect", *args])
    out, err = capsys.readouterr()
    return code, out, err


def _summary(dump: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((dump / "summary.json").read_text())
    return data


def _vendor(calls: list[httpx.Request], fail: bool = False) -> AzureDiEngine:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if fail:
            return httpx.Response(401, json={"error": {"code": "401", "message": "invalid key"}})
        if request.method == "POST":
            return httpx.Response(202, headers={"Operation-Location": "https://op/1"})
        return httpx.Response(200, json=BODY)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return AzureDiEngine(AZURE, client=client, sleep=lambda _: None)


# --------------------------------------------------------------------------- CLI


def test_first_run_writes_the_full_dump(mini_pdf: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(capsys, str(mini_pdf), "--out", "out", "--cache-dir", "cache")
    assert code == 0
    assert out.splitlines()[-1] == "vendor_calls=0"
    assert 'p.3 "Consolidated income statement"' in out

    dump = Path("out/company_x")
    summary = _summary(dump)
    assert summary["page_count"] == 7
    assert summary["parser_skipped"] == ["azure_di"] and summary["parser_failed"] == []
    assert "not set" in summary["engines"]["azure_di"]["reason"]
    assert summary["digital_born"]["is_digitally_born"] is True
    assert {e["page"] for e in summary["keyword_pages_top10"][:2]} == {3, 4}

    lines = [json.loads(line) for line in (dump / "pages.jsonl").read_text().splitlines()]
    assert [line["page"] for line in lines] == list(range(1, 8))
    assert lines[2]["label"] == "140" and lines[2]["tables"]["scanned"] is True
    assert json.loads((dump / "outline.json").read_text())[2] == {
        "level": 2,
        "title": "Consolidated income statement",
        "page": 3,
    }
    text = (dump / "text" / "p0003.txt").read_text()
    assert "Consolidated income statement" in text and "(10,321.2)" in text
    assert json.loads((dump / "tables" / "p0003.json").read_text())["page"] == 3
    assert "13,907.5" in (dump / "tables" / "p0003.txt").read_text()
    thumbs = sorted(p.name for p in (dump / "thumbs").iterdir())
    assert "p0003.png" in thumbs and "p0004.png" in thumbs
    assert not (dump / "azure").exists()


def test_second_run_is_served_from_cache(
    mini_pdf: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(capsys, str(mini_pdf), "--out", "out", "--cache-dir", "cache")
    code, out, _ = _run(capsys, str(mini_pdf), "--out", "out", "--cache-dir", "cache")
    assert code == 0 and out.splitlines()[-1] == "vendor_calls=0"
    stages = {s["stage"]: s for s in _summary(Path("out/company_x"))["run"]["stages"]}
    assert stages["text_layer"]["cache"] == "hit"
    assert stages["pdfplumber_raw"]["cache_hits"] == stages["pdfplumber_raw"]["pages"]


def test_dump_is_deterministic_and_rewritten_whole(
    mini_pdf: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def snapshot() -> dict[str, bytes]:
        root = Path("out/company_x")
        return {
            str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*"))
            if p.is_file() and p.name != "summary.json"
        }

    _run(capsys, str(mini_pdf), "--out", "out", "--cache-dir", "cache-a")
    first, first_summary = snapshot(), _summary(Path("out/company_x"))
    (Path("out/company_x") / "stale.txt").write_text("left over from an older run")
    _run(capsys, str(mini_pdf), "--out", "out", "--cache-dir", "cache-b")  # recomputed, not cached
    assert snapshot() == first
    second_summary = _summary(Path("out/company_x"))
    first_summary.pop("run"), second_summary.pop("run")
    assert first_summary == second_summary
    assert not (Path("out/company_x") / "stale.txt").exists()
    assert [p.name for p in Path("out").iterdir()] == ["company_x"]  # no staging debris


def test_directory_target_inspects_every_pdf(
    tmp_path: Path, mini_pdf_master: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "reports"
    folder.mkdir()
    for name in ("a.pdf", "b.PDF"):
        (folder / name).write_bytes(mini_pdf_master.read_bytes())
    (folder / "notes.txt").write_text("not a pdf")
    code, _, _ = _run(capsys, str(folder), "--out", "out", "--cache-dir", "cache")
    assert code == 0
    assert sorted(p.name for p in Path("out").iterdir()) == ["a", "b"]


def test_refused_upload_exits_1_with_its_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    locked = encrypted_pdf(tmp_path / "locked.pdf", user_password="open-sesame")
    code, out, err = _run(capsys, str(locked), "--out", "out", "--cache-dir", "cache")
    assert code == 1
    assert "refused (encrypted_pdf)" in err
    assert out.splitlines()[-1] == "vendor_calls=0"
    assert not Path("out/locked").exists()


def test_corrupted_cache_entry_fails_loudly(
    mini_pdf: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A damaged cache entry is a failure (exit 1), never silently trusted or a usage error."""
    _run(capsys, str(mini_pdf), "--out", "out", "--cache-dir", "cache")
    [entry] = Path("cache").glob("*/text_layer/*/*/text_layer.json")
    entry.write_text('{"not": "a text layer"}')
    code, out, err = _run(capsys, str(mini_pdf), "--out", "out", "--cache-dir", "cache")
    assert code == 1 and "failed" in err and "TextLayer" in err
    assert out.splitlines()[-1] == "vendor_calls=0"


def test_missing_file_exits_1(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = _run(capsys, "absent.pdf", "--out", "out")
    assert code == 1 and "no such file" in err


def test_usage_errors(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "inspect" in capsys.readouterr().err
    code, _, err = _run(capsys)
    assert code == 2 and "--fixtures" in err
    code, _, err = _run(capsys, "x.pdf", "--azure-pages", "5-2")
    assert code == 2 and "bad page range" in err


def test_fixtures_flag_with_no_pdfs(capsys: pytest.CaptureFixture[str]) -> None:
    Path("fixtures/pdfs").mkdir(parents=True)
    code, out, err = _run(capsys, "--fixtures")
    assert code == 1 and "SOURCES.md" in err and out == ""


def test_not_digitally_born_is_a_specific_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pdf = mini_report(tmp_path / "scanned_like.pdf", blank_pages=2)
    code, out, _ = _run(capsys, str(pdf), "--out", "out", "--cache-dir", "cache")
    assert code == 0
    [warning] = _summary(Path("out/scanned_like"))["warnings"]
    assert warning["code"] == "not_digitally_born"
    assert "2 of 9 pages" in warning["message"] and "pp. 8, 9" in warning["message"]
    assert "NOT digitally born" in out


def test_missing_statement_titles_are_flagged(tmp_path: Path, options: InspectOptions) -> None:
    pdf = encrypted_pdf(tmp_path / "prose_only.pdf", user_password=None)
    result = inspect_pdf(pdf, options)
    codes = [w["code"] for w in result.summary["warnings"]]
    assert "statement_titles_not_found" in codes


def test_tables_all_scans_every_page(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pdf = mini_report(tmp_path / "blanks.pdf", blank_pages=2)
    _run(capsys, str(pdf), "--out", "out", "--cache-dir", "cache")
    assert _summary(Path("out/blanks"))["engines"]["pdfplumber"]["pages"] == [1, 2, 3, 4, 5, 6, 7]
    _run(capsys, str(pdf), "--out", "out", "--cache-dir", "cache", "--tables", "all")
    assert _summary(Path("out/blanks"))["engines"]["pdfplumber"]["pages"] == list(range(1, 10))


def test_table_candidates_keep_statement_titled_pages_beyond_the_top_20() -> None:
    def signals(page: int, titled: bool) -> PageSignals:
        return PageSignals(
            page=page, label=None, chars=500, words=100, replacement_chars=0, has_text=True,
            numeric_token_share=0.0, numeric_rows=0, header_years=(), unit_tokens=(),
            keyword_hits={}, title_lines=("Consolidated balance sheet",) if titled else (),
            title_keyword_hits=("balance sheet",) if titled else (), outline_titles=(), error=None,
        )  # fmt: skip

    ranked = [signals(n, titled=False) for n in range(1, 26)] + [signals(99, titled=True)]
    assert _table_candidates(ranked) == [*range(1, 21), 99]


# --------------------------------------------------------------------------- Azure DI


def test_azure_raw_is_fetched_once_then_cached(mini_pdf: Path, options: InspectOptions) -> None:
    configured = InspectOptions(**{**options.__dict__, "azure": AZURE})
    calls: list[httpx.Request] = []
    first = inspect_pdf(mini_pdf, configured, azure_engine=_vendor(calls))
    assert first.vendor_calls == 1 and len(calls) == 2  # submit + one poll
    assert first.summary["engines"]["azure_di"]["status"] == "ok"
    assert first.summary["parser_skipped"] == []
    assert first.summary["run"]["vendor_cost_usd_estimate"] == 0.07  # 7 pages x $0.01
    raw = first.dump_dir / "azure" / "raw.json"
    assert json.loads(raw.read_text()) == BODY

    again: list[httpx.Request] = []
    second = inspect_pdf(mini_pdf, configured, azure_engine=_vendor(again))
    assert second.vendor_calls == 0 and again == []
    assert second.summary["engines"]["azure_di"]["cache"] == "hit"
    assert second.summary["run"]["vendor_cost_usd_estimate"] == 0.0
    assert json.loads((second.dump_dir / "azure" / "raw.json").read_text()) == BODY


def test_azure_page_scope_is_part_of_the_cache_key(mini_pdf: Path, options: InspectOptions) -> None:
    whole = InspectOptions(**{**options.__dict__, "azure": AZURE})
    scoped = InspectOptions(**{**options.__dict__, "azure": AZURE, "azure_pages": (3, 4)})
    calls: list[httpx.Request] = []
    inspect_pdf(mini_pdf, whole, azure_engine=_vendor(calls))
    result = inspect_pdf(mini_pdf, scoped, azure_engine=_vendor(calls))
    assert result.vendor_calls == 1
    assert calls[-2].url.params["pages"] == "3-4"
    assert result.summary["engines"]["azure_di"]["pages"] == "3-4"


def test_azure_pages_past_the_end_are_refused(mini_pdf: Path, options: InspectOptions) -> None:
    scoped = InspectOptions(**{**options.__dict__, "azure": AZURE, "azure_pages": (7, 8)})
    with pytest.raises(ValueError, match="last page"):
        inspect_pdf(mini_pdf, scoped, azure_engine=_vendor([]))


def test_azure_failure_is_recorded_not_cached_and_the_key_never_leaks(
    mini_pdf: Path, options: InspectOptions
) -> None:
    configured = InspectOptions(**{**options.__dict__, "azure": AZURE})
    calls: list[httpx.Request] = []
    with capture_logs() as logs:
        result = inspect_pdf(mini_pdf, configured, azure_engine=_vendor(calls, fail=True))
    azure = result.summary["engines"]["azure_di"]
    assert azure["status"] == "failed" and azure["code"] == "http_error"
    assert result.summary["parser_failed"] == ["azure_di"]
    assert result.vendor_calls == 1
    assert not (result.dump_dir / "azure").exists()
    assert KEY not in (result.dump_dir / "summary.json").read_text()
    assert KEY not in repr(logs)
    retry = inspect_pdf(mini_pdf, configured, azure_engine=_vendor(calls))
    assert retry.vendor_calls == 1  # a failure is never cached as a result


def test_no_azure_flag_skips_even_with_credentials(
    mini_pdf: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AZURE_DI_ENDPOINT", AZURE.endpoint)
    monkeypatch.setenv("AZURE_DI_KEY", KEY)
    code, out, _ = _run(capsys, str(mini_pdf), "--out", "out", "--cache-dir", "c", "--no-azure")
    assert code == 0 and out.splitlines()[-1] == "vendor_calls=0"
    azure = _summary(Path("out/company_x"))["engines"]["azure_di"]
    assert azure == {"status": "skipped", "reason": "disabled with --no-azure"}


def test_dotenv_credentials_are_read(mini_pdf: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A .env with a key turns Azure on; the blocked network makes the call fail, loudly."""
    Path(".env").write_text(f"AZURE_DI_ENDPOINT={AZURE.endpoint}\nAZURE_DI_KEY='{KEY}'\n")
    code, out, err = _run(capsys, str(mini_pdf), "--out", "out", "--cache-dir", "c")
    assert code == 0 and out.splitlines()[-1] == "vendor_calls=1"
    summary_text = (Path("out/company_x") / "summary.json").read_text()
    assert json.loads(summary_text)["parser_failed"] == ["azure_di"]
    assert KEY not in summary_text and KEY not in out and KEY not in err


# --------------------------------------------------------------------------- logs


def test_logs_never_carry_report_text(mini_pdf: Path, options: InspectOptions) -> None:
    with capture_logs() as logs:
        inspect_pdf(mini_pdf, options)
    events = {entry["event"] for entry in logs}
    assert {"inspect.start", "inspect.stage", "inspect.done"} <= events
    flat = repr(logs)
    assert LOREM[:40] not in flat and "13,907.5" not in flat and "Chief Executive" not in flat
