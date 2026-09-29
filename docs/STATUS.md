# STATUS

Session log. Commands and results only. Newest first.

Toolchain on the tech lead's machine: `uv` 0.12.19 (installed with `python3 -m pip install --user uv`,
binary at `~/Library/Python/3.9/bin/uv`), CPython 3.12.14 via `uv python install 3.12`.

---

## M2.2 — 2026-09-29 — green

M2.2 green. company_a: 20/20 labelled cells found by pdfplumber AND by PyMuPDF, each on its labelled
page, in a value column. Both engines produce identical rows on both goldens. Next M2.3.

| Command | Result |
|---|---|
| `make ci` | exit 0: **488 passed, 0 skipped** |
| `uv run python scripts/gate.py M2.2` | exit 0: pdfplumber 20/20, pymupdf_tables 20/20 |
| `uv run python scripts/gate.py M2.1` | exit 0 (still 7/7) |
| `uv run pytest tests/tables` | grammar, engines, 6 specs x 2 statements x 2 engines, goldens |
| `uv run python scripts/check_scope.py M2.2 --base m2.1` | exit 0 (with the amendment in MILESTONES) |

Tables on the goldens (both engines): Unilever IS p.141 19 rows, columns Notes | EUR m 2024 | 2023 | 2022;
BS p.143 43 rows; Lloyds IS p.216 31 rows (EPS "6.3p" recorded unparsed), BS p.218 44 rows.

What real reports taught this milestone (each is now a test):
- **Engines truncate hanging brackets.** Both grids cut ")" off right-column figures ("(493" for
  "(493)"). Per ADR-001, characters now come from the text layer: the engine's cell box says where,
  the printed words centred in it say what. The engine's own text is kept as `engine_text`.
- **Superscripts split rows.** Unilever's "(a)" footnote marker (4.55 pt) formed its own row and a
  figure row lost its values. Row grouping now attaches undersized glyphs to the row they overlap.
- **Prose fragments look like figures.** PyMuPDF read "d 31 Dece" from the subtitle; the printed
  "31" under it became a "figure". A cell whose edges cut through other words is never a figure.
- **Footnote prose merges columns.** Only figure-like cells (numbers, dashes, note references,
  years) define columns, and columns are measured on printed ink, not engine boxes.
- **Unheaded note columns.** Found by the EXTRACTION section 3 reference pattern (notes_column spec).

Proposed EXTRACTION section 3 amendment (the tech lead owns that document): the note-reference
pattern has no letter suffix, but Unilever prints "4B", "15C", "17A". The "Notes" header caught them
here; code also treats any letter-suffixed reference as a note (it can never be a value).

Carried into M2.3:
- Value-column headers as printed: Unilever "€ million 2024"; Lloyds "2024 £m". Three periods on
  both income statements (2024, 2023, 2022); labels cover two.

---

## M2.1 — 2026-09-29 — green

M2.1 green. company_a IS p.141 (printed 138), BS p.143 (printed 140): equal to the labels, folios too.
Company pages 195-197 detected, none selected. company_b: bank, balance sheet unclassified. Next M2.2.

| Command | Result |
|---|---|
| `make ci` | exit 0: **330 passed** |
| `uv run python scripts/gate.py M2.1` | exit 0, 7/7 PASS |
| `uv run finintel locate company_a --json` | IS [141] labels ['138']; BS [143] labels ['140']; corporate; classified |
| `uv run finintel locate company_b --json` | exit 0; `document_type: bank`, `balance_sheet_classified: false`; parent company BS p.307 rejected |
| `uv run pytest tests/locate/test_synthetic_specs.py tests/locate/test_goldens.py` | 11 passed (4 specs, 4 golden checks) |
| `uv run python scripts/check_scope.py M2.1 --base m1` | exit 0 (with the amendment below) |
| locate on a cached text layer | 0.4-0.5 s per report |

Decisions recorded:
- `total_debt` (tech lead, 2026-09-29): **strict**. A face line "Financial liabilities" that includes
  derivatives and other financial liabilities is not "interest-bearing borrowings"; face-only v1 cannot
  isolate borrowings, so `total_debt` = null with a specific warning and D/E = null (`missing_input`).
  **Needed before M2.4:** the tech lead updates `fixtures/expected/company_a.json` (`total_debt` null,
  plus warning) and `company_a.ratios.json` (D/E null, `reason: missing_input`). Code never edits them.
- M0 layout sign-off: yes. M1 top-10 sign-off: yes (tech lead, 2026-09-29).
- M2.1 allowed paths amended (MILESTONES): the gate calls `finintel locate` (finintel/cli) and the scripted
  check in `scripts/gate.py`, which the original list did not allow.
- Corporate vs other: "customer deposits" alone does not conflict with corporate (housebuilders,
  retailers); "loans and advances to customers", or any two bank signals, does. Tested both ways.

Fixed along the way (M1 bug): `PageText.width/height` came from PyMuPDF's rotated rect while word
coordinates are unrotated, so "top of page" was wrong on landscape pages. Now unrotated, with
`visual_bbox` for display space; `TEXT_LAYER_VERSION` 1 -> 2 so every cached text layer rebuilds.

Evidence for EXTRACTION section 1.1 (thresholds unchanged; the tech lead owns that document):
- Unilever statement pages have numeric-token share 0.26 / 0.29 < 0.30, so numeric density scores 0 on
  both. They still reach 0.80 on title, bookmark, header and vocabulary.

Carried into M2.2:
- Unilever p.141 holds the income statement AND the statement of comprehensive income; "Net profit"
  prints in both. The income-statement table must end at the "Consolidated statement of comprehensive
  income" heading, or `net_income` gets two candidates.
- Unilever's income statement has three value columns (2024, 2023, 2022); labels cover two.
- Lloyds' statement of changes in equity continues onto p.220 ("continued" marker): multi-page merge.

---

## M1 gate re-run — 2026-09-29 — green except sign-off

M1 green on the real fixtures. Unilever 2024 (305 pp., EUR m) and Lloyds 2024 (338 pp., £m) both
inspect cleanly. Labels validate (`validate_pack`: valid). PDF SHA-256 matches the label.

| Command | Result |
|---|---|
| `make ci` | exit 0: **213 passed, 0 skipped** |
| `finintel inspect fixtures/pdfs/company_a.pdf` (cold) | exit 0, 9.8 s; 297/305 pages with text (digitally born); `parser_skipped: ["azure_di"]` |
| `finintel inspect fixtures/pdfs/company_b.pdf` (cold) | exit 0, 12.7 s; 335/338 pages with text |
| second run, both | `vendor_calls=0`; text layer hit; 20/20 pdfplumber pages from cache |
| `summary.page_count` vs `company_a.json` | 305 = 305 |
| `uv run pytest tests/inspect -k holdout` | 13 passed |

Top-10 evidence for the sign-off: company_a balance sheet p.143 rank 2, income statement p.141 rank 3;
company_b balance sheet p.218 rank 1, income statement p.216 rank 2.

Carried into M2.1 (evidence, not yet changes):
- Unilever's statement pages have numeric-token share 0.2565 (p.141) and 0.2932 (p.143): below the
  0.30 density threshold in EXTRACTION section 1.1. Title, outline, header and vocabulary signals
  alone still clear 0.55.
- The parent-company balance sheet (p.197, "COMPANY ACCOUNTS UNILEVER PLC") ranks first by density.
  The company-scope exclusion is what keeps it out.
- Neither PDF defines page labels. The labelled folio ("138") must come from the printed footer.
- Unilever's income statement prints three years (2024, 2023, 2022); labels cover two.
- `total_debt` label = all face "Financial liabilities" (includes derivatives and other financial
  liabilities). Needs a tech-lead decision before M2.4.

---

## M1 — 2026-09-26 — built, gate BLOCKED on fixtures

M1 code complete and green offline. Gate blocked: `fixtures/pdfs/` empty; only `EXAMPLE_company_a.json`.
Not advancing to M2.1.

| Command | Result |
|---|---|
| `make ci` | exit 0: ruff clean, strict mypy clean (64 files), **211 passed, 1 skipped** (`test_fixture_pdfs`: no PDFs), contracts and scope up to date |
| `uv run python scripts/check_scope.py M1 --base m0` | exit 0 |
| `uv run pytest tests/inspect -k holdout` | 13 passed |
| `uv run finintel inspect fixtures/pdfs/company_a.pdf` | exit 1: `no such file`; `vendor_calls=0` |
| `make inspect` (`finintel inspect --fixtures`) | exit 1: `no PDFs found. fixtures/pdfs/ is filled by the tech lead` |
| 280-page synthetic report, cold / warm cache | 1.95 s / 0.22 s (text layer 995 ms, pdfplumber on 40 candidate pages 796 ms). Synthetic pages are lighter than a typeset report; re-measure on `company_a`. |

What `finintel inspect <pdf>` writes to `artifacts/inspect/{stem}/`: `summary.json` (document record,
digital-born score, engines run/skipped/failed, top-10 statement-titled pages, specific warnings, run
trace with per-stage cache status, ms, vendor calls and estimated cost), `pages.jsonl`, `outline.json`,
`text/`, `tables/` (raw pdfplumber, `lines` and `text` strategies), `thumbs/`, `azure/raw.json` when keyed.

Decisions taken inside M1 (no plan change):
- OQ-7 unanswered, so its default applies: Azure DI on the whole document; `--azure-pages` is the B flag.
- Owner-password-only PDFs are accepted (they open without a password; many annual reports restrict
  editing). Only PDFs that need a password to open are refused (`encrypted_pdf`).
- pdfplumber runs on candidate pages by default (top 20 ranked, plus any further statement-titled
  page, max 40); `--tables all` for every page. COST_AND_OPS: never pdfplumber on every page by default.
- An Azure failure of any kind degrades to `parser_failed: ["azure_di"]`, is never cached, and the
  local path completes. Found by a test: a non-httpx network error used to crash the whole run.

Open for the tech lead: the ROCE conflict between the session prompt and `CLAUDE.md` (see the M1 report).

---

## M0 — 2026-09-26 — green

M0 green on Python 3.12. `uv.lock` committed. Sign-off on package layout still open (tech lead).

| Command | Result |
|---|---|
| `uv lock` | resolved 28 packages |
| `make ci` | exit 0: ruff clean, 67 files formatted, strict mypy clean (44 files), 66 passed, contracts up to date, scope.yaml up to date, web guard passed |
| `uv run python scripts/check_scope.py M0 --base main` | exit 0 |
| `uv run python scripts/check_imports.py --forbid fitz,pdfplumber,httpx,anthropic,voyageai` | exit 0 |

Change to the gate machinery: `docs/STATUS.md` added to the G2 global allow-list (MILESTONES G2
row, regenerated `scripts/scope.yaml`), so every session can log here without failing G2.
