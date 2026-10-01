"""`finintel` command line.

    finintel inspect <pdf|dir>... [--fixtures]   M1 inspection dump (see finintel.cli.inspect)
    finintel locate <pdf|fixture> [--json]       M2.1 statement pages and document profile
    finintel extract <pdf|fixture> [--json]      M2.4 StatementPack from the local engines
    finintel eval-e1 <fixture> --engines local   M2.4 golden-cell comparison
    finintel eval-e2 <fixture>                   M3 ratio comparison at 1e-9
    finintel chunks <pdf|fixture> [--json]       M4.1 narrative chunks

Exit codes: 0 ok; 1 a document was refused or failed, or its statements need review; 2 usage;
3 a held-out path was requested.
The last line of `inspect` output is `vendor_calls=N`: paid vendor requests made by this run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from finintel.cli import chunks_cmd, commentary_cmd, extract_cmd
from finintel.cli import locate as locate_cmd
from finintel.cli.common import HoldoutRefusedError
from finintel.cli.inspect import (
    TOP_PAGES,
    InspectOptions,
    InspectUsageError,
    inspect_pdf,
    parse_page_spec,
    report,
    resolve_targets,
)
from finintel.cli.logs import configure_logging
from finintel.cli.settings import Settings, load_settings
from finintel.ingest import MAX_UPLOAD_BYTES, IngestError

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_HOLDOUT = 0, 1, 2, 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="finintel", description="Financial Report Intelligence (research aid)."
    )
    commands = parser.add_subparsers(dest="command")
    inspect = commands.add_parser(
        "inspect",
        help="write an inspection dump for PDFs (M1)",
        description="Page map, outline, text, raw tables and thumbnails for each PDF. "
        "fixtures/holdout/ is always refused.",
    )
    inspect.add_argument("paths", nargs="*", type=Path, help="PDF files or directories of PDFs")
    inspect.add_argument(
        "--fixtures", action="store_true", help="inspect every PDF in fixtures/pdfs/ (not holdout)"
    )
    inspect.add_argument("--out", type=Path, help="dump root (default: artifacts/inspect)")
    inspect.add_argument("--cache-dir", type=Path, help="stage cache (default: artifacts/cache)")
    inspect.add_argument(
        "--no-azure", action="store_true", help="skip Azure DI even if credentials exist"
    )
    inspect.add_argument(
        "--azure-pages", help='restrict Azure DI to pages, e.g. "140-150" (default: all, OQ-7 A)'
    )
    inspect.add_argument(
        "--tables",
        choices=("candidates", "all"),
        default="candidates",
        help="pdfplumber on statement-candidate pages (default) or every page",
    )
    inspect.add_argument(
        "--thumbs", type=int, default=TOP_PAGES, help="thumbnails of the top N ranked pages"
    )
    inspect.add_argument(
        "--max-mb",
        type=float,
        default=MAX_UPLOAD_BYTES / 1_048_576,
        help="refuse files larger than this (default: the 50 MB upload limit)",
    )
    locate = commands.add_parser(
        "locate",
        help="find the primary statement pages and profile the document (M2.1)",
        description="Scores every page that names a statement, rejects company-only and "
        "excluded pages with reasons, follows continuation pages, and decides document type.",
    )
    locate.add_argument("target", help='a PDF path, or a fixture name such as "company_a"')
    locate.add_argument("--json", action="store_true", help="print the full result as JSON")
    locate.add_argument("--cache-dir", type=Path, help="stage cache (default: artifacts/cache)")
    extract = commands.add_parser(
        "extract", help="extract a StatementPack with the local engines (M2.4)"
    )
    extract.add_argument("target", help='a PDF path, or a fixture name such as "company_a"')
    extract.add_argument("--json", action="store_true", help="print the pack as JSON")
    extract.add_argument("--engines", choices=("local", "all"), default="local")
    extract.add_argument("--cache-dir", type=Path)
    chunks = commands.add_parser("chunks", help="chunk the narrative of a report (M4.1)")
    chunks.add_argument("target", help='a PDF path, or a fixture name such as "company_a"')
    chunks.add_argument("--json", action="store_true", help="print all chunks as JSON")
    chunks.add_argument("--cache-dir", type=Path)
    e2p = commands.add_parser("eval-e2", help="compare ratios with fixtures/expected (M3)")
    e2p.add_argument("company", help='fixture name, e.g. "company_a"')
    e2p.add_argument("--cache-dir", type=Path)
    cm = commands.add_parser("commentary", help="grounded commentary for a report (M5.2)")
    cm.add_argument("company", help='fixture name, e.g. "company_a"')
    cm.add_argument("--replay", type=Path, help="replay the recorded model calls in this artefact")
    cm.add_argument("--embedder", choices=("bge-m3", "fake"), default="bge-m3")
    cm.add_argument("--cache-dir", type=Path)
    e3p = commands.add_parser("eval-e3", help="retrieval hit@8 against labelled queries (M4.2)")
    e3p.add_argument("company", help='fixture name, e.g. "company_a"')
    e3p.add_argument("--labels", type=Path, help="label file (default fixtures/expected/...)")
    e3p.add_argument("--backend", choices=("memory", "postgres"), default="memory")
    e3p.add_argument("--embedder", choices=("bge-m3", "fake"), default="bge-m3")
    e3p.add_argument("--cache-dir", type=Path)
    e1 = commands.add_parser("eval-e1", help="compare an extraction with fixtures/expected (M2.4)")
    e1.add_argument("company", help='fixture name, e.g. "company_a"')
    e1.add_argument("--engines", choices=("local", "all"), default="local")
    e1.add_argument("--cache-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help(sys.stderr)
        return EXIT_USAGE
    try:
        settings = load_settings()
    except ValueError as exc:
        print(f"finintel: {exc}", file=sys.stderr)
        return EXIT_USAGE
    configure_logging(settings.log_format, settings.log_level)
    if args.command == "locate":
        return _locate(args, settings)
    if args.command in ("extract", "eval-e1"):
        return _extract(args, settings)
    if args.command == "eval-e2":
        return _eval_e2(args, settings)
    if args.command == "commentary":
        return _commentary(args, settings)
    if args.command == "eval-e3":
        return _eval_e3(args, settings)
    if args.command == "chunks":
        return _chunks(args, settings)
    return _inspect(args, settings)


def _extract(args: argparse.Namespace, settings: Settings) -> int:
    cache_dir = args.cache_dir or settings.cache_dir
    try:
        if args.command == "extract":
            pdf, result, out = extract_cmd.run_extract(
                args.target, cache_dir, settings.artifacts_dir, args.engines, settings.azure
            )
            if args.json and result.pack is not None:
                print(json.dumps(result.pack, indent=2))
            else:
                extract_cmd.print_summary(pdf, result, out, sys.stdout)
            return EXIT_OK if result.status == "ok" and not result.schema_errors else EXIT_FAILED
        report, path = extract_cmd.run_e1(
            args.company, args.engines, cache_dir, settings.artifacts_dir, settings.azure
        )
    except HoldoutRefusedError as exc:
        print(f"finintel: refused {exc}: held out until M8.3", file=sys.stderr)
        return EXIT_HOLDOUT
    except (FileNotFoundError, ValueError, RuntimeError, IngestError) as exc:
        print(f"finintel {args.command}: {exc}", file=sys.stderr)
        return EXIT_FAILED
    e1 = report["e1"]
    print(
        f"{report['company']}: labelled {e1['labelled']}  matched {e1['matched']}  "
        f"honest_null {e1['honest_null']}  silent_wrong {e1['silent_wrong']}  "
        f"unit_errors {e1['unit_errors']}"
    )
    for cell in e1["cells"]:
        if cell["status"] != "matched":
            print(
                f"  {cell['status']}: {cell['item']} {cell['period']} "
                f"expected {cell['expected']} got {cell['got']}"
            )
    print(f"  -> {path}")
    return EXIT_OK


def _locate(args: argparse.Namespace, settings: Settings) -> int:
    try:
        pdf, sha256, result = locate_cmd.locate_pdf(
            args.target, args.cache_dir or settings.cache_dir
        )
    except HoldoutRefusedError as exc:
        print(f"finintel locate: refused {exc}: held out until M8.3", file=sys.stderr)
        return EXIT_HOLDOUT
    except FileNotFoundError as exc:
        print(f"finintel locate: {exc}", file=sys.stderr)
        return EXIT_FAILED
    except IngestError as exc:
        print(f"finintel locate: refused ({exc.code.value}): {exc.message}", file=sys.stderr)
        return EXIT_FAILED
    if args.json:
        locate_cmd.dump_json(pdf, sha256, result, sys.stdout)
    else:
        locate_cmd.report(pdf, result, sys.stdout)
    return locate_cmd.exit_code(result)


def _inspect(args: argparse.Namespace, settings: Settings) -> int:
    if not args.paths and not args.fixtures:
        print("finintel inspect: give PDF paths or --fixtures", file=sys.stderr)
        return EXIT_USAGE
    try:
        azure_pages = parse_page_spec(args.azure_pages) if args.azure_pages else None
        targets = resolve_targets(args.paths, fixtures=args.fixtures)
    except HoldoutRefusedError as exc:
        print(
            f"finintel inspect: refused {exc}: fixtures/holdout/ is held out until M8.3 "
            "(docs/EVAL.md section 1)",
            file=sys.stderr,
        )
        return EXIT_HOLDOUT
    except (ValueError, FileNotFoundError) as exc:
        print(f"finintel inspect: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if not targets:
        print(
            "finintel inspect: no PDFs found. fixtures/pdfs/ is filled by the tech lead "
            "(fixtures/pdfs/SOURCES.md).",
            file=sys.stderr,
        )
        return EXIT_FAILED

    options = InspectOptions(
        out_dir=args.out or settings.artifacts_dir / "inspect",
        cache_dir=args.cache_dir or settings.cache_dir,
        azure=settings.azure,
        azure_enabled=not args.no_azure,
        azure_pages=azure_pages,
        tables=args.tables,
        thumbs=max(args.thumbs, 0),
        max_bytes=int(args.max_mb * 1_048_576),
    )
    code, vendor_calls = EXIT_OK, 0
    for target in targets:
        try:
            result = inspect_pdf(target, options)
        except FileNotFoundError:
            print(f"{target}: no such file", file=sys.stderr)
            code = max(code, EXIT_FAILED)
            continue
        except IngestError as exc:
            print(f"{target.name}: refused ({exc.code.value}): {exc.message}", file=sys.stderr)
            code = max(code, EXIT_FAILED)
            continue
        except InspectUsageError as exc:
            print(f"{target.name}: {exc}", file=sys.stderr)
            code = max(code, EXIT_USAGE)
            continue
        except ValueError as exc:  # e.g. an unreadable cache entry: a failure, not a usage error
            print(f"{target.name}: failed: {exc}", file=sys.stderr)
            code = max(code, EXIT_FAILED)
            continue
        vendor_calls += result.vendor_calls
        report(result, sys.stdout)
    print(f"vendor_calls={vendor_calls}")
    return code


def _eval_e2(args: argparse.Namespace, settings: Settings) -> int:
    try:
        report, path = extract_cmd.run_e2(
            args.company, args.cache_dir or settings.cache_dir, settings.artifacts_dir
        )
    except HoldoutRefusedError as exc:
        print(f"finintel: refused {exc}: held out until M8.3", file=sys.stderr)
        return EXIT_HOLDOUT
    except (FileNotFoundError, ValueError, RuntimeError, IngestError) as exc:
        print(f"finintel eval-e2: {exc}", file=sys.stderr)
        return EXIT_FAILED
    e2 = report["e2"]
    print(
        f"{report['company']}: ratio cells expected {e2['expected']}  matched {e2['matched']} "
        f"(extracted {e2['matched_extracted']}, labelled {e2['matched_labelled']}) "
        f"at {e2['tolerance']}"
    )
    for cell in e2["cells"]:
        if cell["extracted"] != "ok" or cell["labelled"] != "ok":
            print(
                f"  {cell['period']} {cell['ratio']}: extracted {cell['extracted']}; "
                f"labelled {cell['labelled']}"
            )
    print(f"  -> {path}")
    return EXIT_OK


def _commentary(args: argparse.Namespace, settings: Settings) -> int:
    import os

    from finintel.cli.settings import read_dotenv

    env = {**read_dotenv(Path(".env")), **os.environ}
    try:
        run, report, path = commentary_cmd.run_commentary(
            args.company,
            args.cache_dir or settings.cache_dir,
            settings.artifacts_dir,
            env,
            replay=args.replay,
            embedder_name=args.embedder,
        )
    except HoldoutRefusedError as exc:
        print(f"finintel: refused {exc}: held out until M8.3", file=sys.stderr)
        return EXIT_HOLDOUT
    except (FileNotFoundError, ValueError, RuntimeError, KeyError, IngestError) as exc:
        print(f"finintel commentary: {exc}", file=sys.stderr)
        return EXIT_FAILED
    c = run.commentary
    label = f"  [{c.label}]" if c.label else ""
    print(f"{args.company}: mode={c.mode}{label}")
    if run.fallback_reason:
        print(f"  model unavailable ({run.fallback_reason}): fell back to extractive")
    print(f"  numbers: {run.snapshot['rendered']}")
    for topic in c.topics:
        print(f"  {topic.topic}: {topic.status}, {len(topic.paragraphs)} paragraph(s)")
    print(f"  executive_summary: {c.executive_summary.status}, {len(c.executive_summary.bullets)}")
    print(f"  e4 {report['e4']}")
    for key in ("e8", "qa"):
        if key in report:
            print(f"  {key} {report[key]}")
    for note in report["notes"]:
        print(f"  {note}")
    print(f"  -> {path}")
    return EXIT_OK


def _eval_e3(args: argparse.Namespace, settings: Settings) -> int:
    try:
        report, path = extract_cmd.run_e3(
            args.company,
            args.cache_dir or settings.cache_dir,
            settings.artifacts_dir,
            args.labels,
            args.backend,
            args.embedder,
        )
    except HoldoutRefusedError as exc:
        print(f"finintel: refused {exc}: held out until M8.3", file=sys.stderr)
        return EXIT_HOLDOUT
    except (FileNotFoundError, ValueError, RuntimeError, IngestError) as exc:
        print(f"finintel eval-e3: {exc}", file=sys.stderr)
        return EXIT_FAILED
    e3 = report["e3"]
    print(
        f"{report['company']}: hit@8 {e3['hits']}/{e3['queries']} = {e3['hit_at_8']:.2f}  "
        f"page basis {e3['page_basis']} (folio offset {e3['folio_offset']})  models {e3['models']}"
    )
    for cell in e3["cells"]:
        print(
            f"  {'HIT ' if cell['hit'] else 'MISS'} {cell['q']}  "
            f"want pdf {cell['expected_pdf_pages']}"
        )
        if not cell["hit"]:
            for r in cell["retrieved"]:
                print(
                    f"       got pdf {r['pdf_pages']}  {r['section']}  "
                    f"{' > '.join(r['heading_path'])}"
                )
    print(f"  -> {path}")
    return EXIT_OK


def _chunks(args: argparse.Namespace, settings: Settings) -> int:
    try:
        pdf, sha, chunks, excluded = chunks_cmd.chunk_pdf(
            args.target, args.cache_dir or settings.cache_dir
        )
    except HoldoutRefusedError as exc:
        print(f"finintel chunks: refused {exc}: held out until M8.3", file=sys.stderr)
        return EXIT_HOLDOUT
    except (FileNotFoundError, IngestError) as exc:
        print(f"finintel chunks: {exc}", file=sys.stderr)
        return EXIT_FAILED
    if args.json:
        chunks_cmd.dump_json(pdf, sha, chunks, excluded, sys.stdout)
    else:
        chunks_cmd.report(pdf, chunks, excluded, sys.stdout)
    return EXIT_OK
