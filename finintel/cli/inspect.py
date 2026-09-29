"""`finintel inspect`: the M1 PDF inspection toolkit.

For each PDF, writes `{out}/{stem}/`:

    summary.json          document record, digital-born score, engines run or skipped, the top
                          statement-titled pages, warnings, and the run trace (cache, timings,
                          vendor calls, estimated vendor cost)
    pages.jsonl           one line per page: text stats, numeric density, keyword hits, title
                          lines, bookmarks, table counts, inspection rank
    outline.json          PDF bookmarks with 1-based target pages
    text/pNNNN.txt        page text in PyMuPDF reading order, verbatim
    tables/pNNNN.json     raw pdfplumber tables (candidate pages, or every page with --tables all)
    tables/pNNNN.txt      the same tables as pipe-separated rows, for reading
    thumbs/pNNNN.png      thumbnails of the top-ranked pages
    azure/raw.json        raw Azure DI prebuilt-layout response, when credentials exist

No mapping, units or ratios: those start in M2. Held-out reports are refused (EVAL section 1).
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

import structlog

from finintel import PIPELINE_VERSION
from finintel.cache import StageCache, StageKey
from finintel.cli.common import FIXTURE_PDFS, HoldoutRefusedError, cached_text_layer, is_holdout
from finintel.cli.dump import write_dump
from finintel.cli.page_signals import (
    STATEMENT_KEYWORDS,
    PageSignals,
    page_signals,
    rank_pages,
    statement_hits,
)
from finintel.ingest import (
    MAX_UPLOAD_BYTES,
    DigitalBornScore,
    DocumentRecord,
    ingest,
    score_digital_born,
)
from finintel.parse.engines.azure_di_engine import (
    RAW_RESPONSE_VERSION,
    USD_PER_PAGE,
    AzureDiConfig,
    AzureDiEngine,
    AzureDiError,
    page_ranges,
)
from finintel.parse.engines.pdfplumber_engine import (
    RAW_TABLES_VERSION,
    PdfplumberEngine,
    RawPageTables,
)
from finintel.parse.text_layer import EXTRACTOR, TextLayer, render_page_png

INSPECT_VERSION = "1"
TOP_PAGES = 10
TABLE_CANDIDATES = 20
TABLE_CANDIDATES_MAX = 40

log = structlog.get_logger(__name__)


class InspectUsageError(ValueError):
    """An option that cannot apply to this document (exit code 2)."""


@dataclass(frozen=True)
class InspectOptions:
    out_dir: Path
    cache_dir: Path
    azure: AzureDiConfig | None
    azure_enabled: bool = True
    azure_pages: tuple[int, ...] | None = None  # None: whole document (OQ-7 default A)
    tables: str = "candidates"  # "candidates" or "all"
    thumbs: int = TOP_PAGES
    max_bytes: int = MAX_UPLOAD_BYTES


@dataclass(frozen=True)
class InspectResult:
    pdf: Path
    dump_dir: Path
    summary: dict[str, Any]
    ranked: tuple[PageSignals, ...]

    @property
    def vendor_calls(self) -> int:
        calls: int = self.summary["run"]["vendor_calls"]
        return calls


@dataclass
class _Trace:
    stages: list[dict[str, Any]] = field(default_factory=list)
    vendor_calls: int = 0
    vendor_cost_usd: float = 0.0

    def stage(self, name: str, started: float, **detail: Any) -> None:
        ms = round((time.perf_counter() - started) * 1000, 1)
        self.stages.append({"stage": name, "ms": ms, **detail})
        log.info("inspect.stage", stage=name, ms=ms, **detail)


# ---------------------------------------------------------------------------- targets


def resolve_targets(paths: Sequence[Path], *, fixtures: bool) -> list[Path]:
    """Expand directories to their *.pdf files (not recursive) and refuse held-out paths.

    `--fixtures` means `fixtures/pdfs/*.pdf` only, never `fixtures/holdout/` (EVAL section 1).
    """
    requested = [*paths, *([FIXTURE_PDFS] if fixtures else [])]
    targets: list[Path] = []
    for path in requested:
        if is_holdout(path):
            raise HoldoutRefusedError(str(path))
        if path.is_dir():
            files = sorted(p for p in path.iterdir() if p.suffix.lower() == ".pdf" and p.is_file())
        else:
            files = [path]
        for file in files:
            if is_holdout(file):
                raise HoldoutRefusedError(str(file))
            targets.append(file)
    return targets


def parse_page_spec(spec: str) -> tuple[int, ...]:
    """Parse "1-3,7" into (1, 2, 3, 7)."""
    pages: set[int] = set()
    for part in spec.split(","):
        start, _, end = part.strip().partition("-")
        first, last = int(start), int(end or start)
        if first < 1 or last < first:
            raise ValueError(f"bad page range {part!r}")
        pages.update(range(first, last + 1))
    return tuple(sorted(pages))


# ---------------------------------------------------------------------------- one PDF


def inspect_pdf(
    pdf_path: Path,
    options: InspectOptions,
    *,
    azure_engine: AzureDiEngine | None = None,
    table_engine: PdfplumberEngine | None = None,
) -> InspectResult:
    """Inspect one PDF and write its dump. Raises IngestError for refused uploads."""
    if is_holdout(pdf_path):
        raise HoldoutRefusedError(str(pdf_path))
    trace = _Trace()
    run_started = time.perf_counter()

    started = time.perf_counter()
    record = ingest(pdf_path, max_bytes=options.max_bytes)
    trace.stage("ingest", started, sha256=record.sha256[:12], pages=record.page_count)
    log.info("inspect.start", file=record.filename, sha256=record.sha256[:12])
    cache = StageCache(options.cache_dir)

    layer = _text_layer(pdf_path, record, cache, trace)
    score = score_digital_born(layer)
    signals = [page_signals(page, layer.outline) for page in layer.pages]
    ranked = rank_pages(signals)

    if options.tables == "all":
        table_pages = list(range(1, layer.page_count + 1))
    else:
        table_pages = _table_candidates(ranked)
    tables = _raw_tables(pdf_path, record.sha256, table_pages, cache, trace, table_engine)

    azure_status, azure_raw = _azure(pdf_path, record, layer, options, cache, trace, azure_engine)

    started = time.perf_counter()
    thumbs = {s.page: render_page_png(pdf_path, s.page) for s in ranked[: options.thumbs]}
    trace.stage("thumbnails", started, pages=len(thumbs))

    summary = _summary(record, layer, score, ranked, table_pages, tables, azure_status, options)
    summary["run"] = {
        "vendor_calls": trace.vendor_calls,
        "vendor_cost_usd_estimate": round(trace.vendor_cost_usd, 4),
        "total_ms": round((time.perf_counter() - run_started) * 1000, 1),
        "stages": trace.stages,
    }
    rank_of = {s.page: i for i, s in enumerate(ranked, start=1)}
    tables_by_page = {t.page: t for t in tables}
    pages = [_page_line(s, rank_of.get(s.page), tables_by_page.get(s.page)) for s in signals]

    dump_dir = options.out_dir / pdf_path.stem
    write_dump(
        dump_dir,
        summary=summary,
        pages=pages,
        outline=[e.model_dump(mode="json") for e in layer.outline],
        texts={p.page: p.text for p in layer.pages},
        tables=tables,
        thumbs=thumbs,
        azure_raw=azure_raw,
    )
    log.info("inspect.done", file=record.filename, dump=str(dump_dir), **summary["run"])
    return InspectResult(pdf_path, dump_dir, summary, tuple(ranked))


def _text_layer(pdf: Path, record: DocumentRecord, cache: StageCache, trace: _Trace) -> TextLayer:
    started = time.perf_counter()
    layer, hit = cached_text_layer(pdf, record.sha256, cache)
    trace.stage("text_layer", started, cache="hit" if hit else "miss")
    return layer


def _table_candidates(ranked: Sequence[PageSignals]) -> list[int]:
    """Top-ranked pages, plus any further page titled as a statement, capped."""
    chosen = [s.page for s in ranked[:TABLE_CANDIDATES]]
    chosen += [s.page for s in ranked[TABLE_CANDIDATES:] if s.titled_as_statement]
    return sorted(chosen[:TABLE_CANDIDATES_MAX])


def _raw_tables(
    pdf: Path,
    sha256: str,
    pages: Sequence[int],
    cache: StageCache,
    trace: _Trace,
    engine: PdfplumberEngine | None,
) -> list[RawPageTables]:
    started = time.perf_counter()
    engine = engine or PdfplumberEngine()
    keys = {
        n: StageKey.build(
            sha256, "pdfplumber_raw", RAW_TABLES_VERSION, {"pdfplumber": engine.version, "page": n}
        )
        for n in pages
    }
    found: dict[int, RawPageTables] = {}
    for n, key in keys.items():
        data = cache.get(key, "tables.json")
        if data is not None:
            found[n] = RawPageTables.model_validate_json(data)
    missing = [n for n in pages if n not in found]
    for result in engine.raw_tables(pdf, missing) if missing else []:
        cache.put(keys[result.page], {"tables.json": result.model_dump_json().encode("utf-8")})
        found[result.page] = result
    trace.stage("pdfplumber_raw", started, pages=len(pages), cache_hits=len(pages) - len(missing))
    return [found[n] for n in pages]


def _azure(
    pdf: Path,
    record: DocumentRecord,
    layer: TextLayer,
    options: InspectOptions,
    cache: StageCache,
    trace: _Trace,
    engine: AzureDiEngine | None,
) -> tuple[dict[str, Any], Path | None]:
    if not options.azure_enabled:
        return {"status": "skipped", "reason": "disabled with --no-azure"}, None
    config = options.azure
    if config is None:
        return {
            "status": "skipped",
            "reason": "AZURE_DI_ENDPOINT and AZURE_DI_KEY are not set",
        }, None
    if options.azure_pages and max(options.azure_pages) > layer.page_count:
        raise InspectUsageError(f"--azure-pages goes past the last page ({layer.page_count})")

    started = time.perf_counter()
    pages = page_ranges(options.azure_pages) if options.azure_pages else None
    key = StageKey.build(
        record.sha256, "azure_di_raw", RAW_RESPONSE_VERSION, config.cache_config(pages)
    )
    status: dict[str, Any] = {
        "model_id": config.model_id,
        "api_version": config.api_version,
        "pages": pages or "all",
    }
    hit = cache.has(key)
    if not hit:
        trace.vendor_calls += 1
        try:
            body = (engine or AzureDiEngine(config)).analyze_raw(pdf.read_bytes(), pages)
        except AzureDiError as exc:
            trace.stage("azure_di_raw", started, cache="miss", status="failed", code=exc.code)
            return {**status, "status": "failed", "code": exc.code, "reason": str(exc)}, None
        analysed = len((body.get("analyzeResult") or {}).get("pages") or ())
        trace.vendor_cost_usd += analysed * USD_PER_PAGE
        cache.put(key, {"raw.json": json.dumps(body, ensure_ascii=False).encode("utf-8")})
    trace.stage("azure_di_raw", started, cache="hit" if hit else "miss", status="ok")
    return {**status, "status": "ok", "cache": "hit" if hit else "miss"}, cache.path(
        key
    ) / "raw.json"


# ---------------------------------------------------------------------------- summary


def _summary(
    record: DocumentRecord,
    layer: TextLayer,
    score: DigitalBornScore,
    ranked: Sequence[PageSignals],
    table_pages: Sequence[int],
    tables: Sequence[RawPageTables],
    azure: dict[str, Any],
    options: InspectOptions,
) -> dict[str, Any]:
    engines: dict[str, dict[str, Any]] = {
        "pymupdf": {"status": "ok", "extractor": EXTRACTOR},
        "pdfplumber": {
            "status": "ok",
            "version": PdfplumberEngine.version,
            "scope": options.tables,
            "pages": list(table_pages),
            "failed_pages": [t.page for t in tables if t.error],
        },
        "azure_di": azure,
    }
    return {
        "inspect_version": INSPECT_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "file": record.filename,
        "sha256": record.sha256,
        "page_count": layer.page_count,
        "document": record.model_dump(mode="json"),
        "digital_born": score.model_dump(mode="json"),
        "warnings": _warnings(layer, score, ranked),
        "page_labels": layer.has_page_labels,
        "outline_entries": len(layer.outline),
        "outline_statement_entries": [
            {"title": e.title, "page": e.page} for e in layer.outline if statement_hits(e.title)
        ],
        "keyword_pages_top10": [_top_entry(s) for s in ranked[:TOP_PAGES]],
        "engines": engines,
        "parser_skipped": sorted(k for k, v in engines.items() if v["status"] == "skipped"),
        "parser_failed": sorted(k for k, v in engines.items() if v["status"] == "failed"),
    }


def _warnings(
    layer: TextLayer, score: DigitalBornScore, ranked: Sequence[PageSignals]
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if not score.is_digitally_born:
        failing = score.failing_pages
        shown = ", ".join(str(p) for p in failing[:12]) + (" …" if len(failing) > 12 else "")
        warnings.append(
            {
                "code": "not_digitally_born",
                "message": f"{len(failing)} of {score.pages_total} pages have fewer than "
                f"{score.min_extractable_chars} extractable characters (pp. {shown}); "
                f"OCR-derived values will be review suggestions only",
                "page": None,
            }
        )
    for page in layer.pages:
        if page.error:
            warnings.append(
                {
                    "code": "page_unreadable",
                    "message": f"p.{page.page}: {page.error}",
                    "page": page.page,
                }
            )
    if not any(s.titled_as_statement for s in ranked):
        warnings.append(
            {
                "code": "statement_titles_not_found",
                "message": "no page has a primary-statement title in its title region or bookmarks",
                "page": None,
            }
        )
    return warnings


def _top_entry(s: PageSignals) -> dict[str, Any]:
    return {
        "page": s.page,
        "label": s.label,
        "title": s.title_lines[0] if s.title_lines else None,
        "titled_as_statement": s.titled_as_statement,
        "table_like": s.table_like,
        "numeric_rows": s.numeric_rows,
        "statement_mentions": sum(s.keyword_hits[k] for k in STATEMENT_KEYWORDS),
        "unit_tokens": list(s.unit_tokens),
        "header_years": list(s.header_years),
    }


def _page_line(s: PageSignals, rank: int | None, tables: RawPageTables | None) -> dict[str, Any]:
    line = s.model_dump(mode="json")
    line["inspect_rank"] = rank
    line["tables"] = (
        {
            "scanned": True,
            "lines": tables.count("lines"),
            "text": tables.count("text"),
            "error": tables.error,
        }
        if tables
        else {"scanned": False}
    )
    return line


# ---------------------------------------------------------------------------- report


def report(result: InspectResult, out: TextIO) -> None:
    """A short human summary of one inspection."""
    s = result.summary
    db = s["digital_born"]
    born = "digitally born" if db["is_digitally_born"] else "NOT digitally born"
    print(
        f"{s['file']}  {s['page_count']} pages  sha256 {s['sha256'][:12]}  "
        f"{born} ({db['pages_passing']}/{db['pages_total']} pages with text)",
        file=out,
    )
    titled = [t for t in s["keyword_pages_top10"] if t["titled_as_statement"]][:6]
    if titled:
        pages = " · ".join(
            f'p.{t["page"]} "{t["title"] or "(bookmark)"}"{" [table]" if t["table_like"] else ""}'
            for t in titled
        )
        print(f"  statement-titled pages: {pages}", file=out)
    engines = s["engines"]
    plumber = engines["pdfplumber"]
    azure = engines["azure_di"]
    azure_text = azure["status"] + (f" ({azure['reason']})" if azure.get("reason") else "")
    print(
        f"  pdfplumber: {len(plumber['pages'])} pages · azure_di: {azure_text}",
        file=out,
    )
    for warning in s["warnings"]:
        print(f"  warning {warning['code']}: {warning['message']}", file=out)
    print(f"  -> {result.dump_dir}", file=out)
