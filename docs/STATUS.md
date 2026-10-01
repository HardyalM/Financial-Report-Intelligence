# STATUS

Session log. Commands and results only. Newest first.

Toolchain on the tech lead's machine: `uv` 0.12.19 (installed with `python3 -m pip install --user uv`,
binary at `~/Library/Python/3.9/bin/uv`), CPython 3.12.14 via `uv python install 3.12`.

---

## M4.1 — 2026-10-01 — green (heading_path sign-off pending)

M4.1 green. company_a: 1,208 chunks, every one with `page_start`; 0 chunks in primary or company statements;
0 on excluded statement pages; 0 prose lines overlapping an independent table region (978 prose chunks).
No database. Next M4.2 (needs Docker/Postgres and `fixtures/expected/company_a.retrieval.json` from the tech lead).

| Command | Result |
|---|---|
| `make ci` | exit 0: **749 passed, 0 skipped** |
| `uv run python scripts/gate.py M4.1` | exit 0, 4/4 PASS |
| `uv run python scripts/check_scope.py M4.1 --base m3` | exit 0 (ruled_tables.py amendment in MILESTONES) |

Caveat: the independent table check unions the density detector with the same PyMuPDF ruled-table finder
production uses, so it is partly a wiring check, not a fully independent oracle.
Open: tech-lead sign-off "10 random chunks have correct heading_path values".

---

## M3 — 2026-10-01 — green

M3 green. ROCE 0.172426443613 (FY2024) and 0.188527599065 (FY2023) match the hand calculator at 1e-9.
Operating margin 0.154704 / 0.163714, current ratio 0.760640 / 0.761560. Debt-to-equity null,
`missing_input` (total_debt is null). unit_scale millions, EUR. Next M4.1.

| Command | Result |
|---|---|
| `make ci` | exit 0: **688 passed, 0 skipped** |
| `make eval-e2 COMPANY=company_a` | 8/8 cells expected, matched from the labelled pack AND from the pipeline's pack |
| `uv run python scripts/gate.py M3` | exit 0 (`e2.matched == e2.expected`) |
| `uv run python scripts/check_scope.py M3 --base m2.5` | exit 0 (with the amendment in MILESTONES) |

What shipped (finintel/ratios/engine.py, schemas/ratio_pack.schema.json, generated contract):
- The four locked ratios from the StatementPack only; exact Decimal division, converted once to float.
  pandas was not needed for four quotients.
- A null input gives `value: null`, `reason: "missing_input"` (CLAUDE.md wording) and names the input.
  A zero denominator gives `division_by_zero`. Negative equity or capital employed: the value is shown with
  `negative_denominator` beside it (ADR-008), plus a pack warning.
- `applicability` is separate: bank `not_applicable` (all four); unclassified balance sheet makes the current
  ratio `not_applicable`; `other` withholds the rest; NHS withholds all but the current ratio until OQ-5 is
  decided. A hidden-by-applicability ratio shows no number even if its inputs exist.
- A v1.0.0 pack has no document profile: treated as corporate, its own nulls decide. Stated in the docstring.
- Inputs carry item, value, page and badges (`derived`, `manual`, `manual_unanchored`). `total_debt` on
  a derived pack shows `derived` and no page.
- Changes: margin and ROCE in percentage points, multiples absolute, items absolute and percent; a
  null never turns into a number and a zero base gives a null percent. Periods sorted latest first.
- `statement_pack_sha` is the SHA-256 of the canonical pack JSON, so stale ratios are detectable.
- Drift test reads the formula strings out of CLAUDE.md and compares them with the code.
- Property test: multiplying every input by 1,000 changes no ratio, flag or reason (300 examples).

Notes:
- Unilever's FY2022 period (income statement only) gets ratios with missing balance-sheet inputs. Honest,
  but a UI decision for M7: show a prior-year column only when it has inputs.
- Tag `m3-done` (the web-directory guard, G5) is the tech lead's to create.
- Still pending from earlier: Azure key (M2.5 gate) and ADR-010 review of the six M2.3 specs.

---

## M2.5 — 2026-10-01 — BUILT, gate BLOCKED on an Azure DI key

M2.5 code complete and green offline. The gate command cannot pass honestly: no Azure key, so no real
response exists. Not advancing to M2.6/M3 claims; M3 does not depend on Azure and can proceed.

| Command | Result |
|---|---|
| `make ci` | exit 0: **656 passed, 0 skipped** |
| `make eval-e1 COMPANY=company_a ENGINES=all` (no key) | 22/22 matched, 0 silent wrong, Azure `engine_skipped: no credentials`, `reduced_verification` raised |
| `uv run python scripts/gate.py M2.5` | **exit 1: `FAIL azure.ran == True`** (by design: a skipped engine must not look like a pass) |
| `uv run python scripts/check_scope.py M2.5 --base m2.4` | exit 0 (with the amendment in MILESTONES) |

Built (tested on an Azure-shaped stand-in, tests/extract/fake_azure.py; NOT a recorded vendor response):
- `normalise_layout`: Azure layout JSON (inches, per-cell bounding regions) to ParsedTables in PDF points.
- Anchoring for non-text-layer engines: a figure the engine reports but the page does not print at that
  spot is an `unanchored_candidate` and is dropped. Verified: a "corrected" 12,600 never appears.
  Characters, row, column and period always come from the text layer (`row_source: text_layer`).
- Family voting: two families on the same cell x1.00 (else x0.90), engine `reconciled`; a cross-engine
  difference is resolved only if exactly one candidate passes every applicable arithmetic check (capped
  0.85), else null + `parser_disagreement`. Review items listed in the report.
- Azure called on the statement pages only (OQ-7 option B, about $0.08 a report), raw response cached;
  no key or a vendor failure gives `engine_skipped` and the local path unchanged.
- Tie-break tests: resolved by arithmetic (revenue) and unresolved when no check applies (cash).

Honest limits:
- Real Azure behaviour is unverified. Real layouts may split cells, merge rows or round coordinates in
  ways the stand-in does not; the anchoring rule is the safety net, but E1 on real output is the test.
- Because row/column/period are always text-layer derived, cross-family disagreement can only arise from
  which cells survive anchoring, so the second family mostly adds corroboration (x1.00) and a tripwire.
- tau calibration: note added to EXTRACTION 5.3 saying unchanged and pending real two-family evidence.

Needed from the tech lead to close M2.5: set `AZURE_DI_ENDPOINT` and `AZURE_DI_KEY` in `.env`, then
`make eval-e1 COMPANY=company_a ENGINES=all && python scripts/gate.py M2.5`. One disputed-cell sign-off
also remains (MILESTONES). Also pending from M2.3: ADR-010 review of the six new synthetic specs.

---

## M2.4 — 2026-09-30 — green

M2.4 green. E1 company_a: 22/22 matched (20 figures + 2 explicit `total_debt` nulls), silent_wrong 0,
unit_errors 0, published_llm_pointer 0. `total_debt` null with a specific warning. Next M2.5.

| Command | Result |
|---|---|
| `make ci` | exit 0: **646 passed, 0 skipped** |
| `make eval-e1 COMPANY=company_a ENGINES=local` | labelled 22, matched 22, honest_null 0, silent_wrong 0, unit_errors 0 |
| `uv run python scripts/gate.py M2.4` | exit 0 (4/4); M2.1-M2.3 gates still exit 0 |
| `uv run python scripts/check_scope.py M2.4 --base m2.3` | exit 0 (with the amendment in MILESTONES) |
| `uv run finintel extract company_b` | bank: every corporate item an explicit null, bank_layout + unclassified_balance_sheet warnings |

Label change (tech lead, 2026-09-30, commit c3418ee, CHANGELOG entry): company_a `total_debt` and
debt_to_equity are null under the strict rule. Unilever's face "Financial liabilities" includes derivatives
(594) and other financial liabilities (804), so it is not interest-bearing borrowings + leases.

What the pipeline does (finintel/extract.py): ingest, text layer, locate, both text-layer engines,
headers, alias-map mapping, arithmetic checks, publish-or-null.
- Confidence: base (exact .95, regex .90, structural .85) x 0.90 (one engine family), +0.05 if a check
  passes, -0.30 if one fails (failure dominates), cap 0.99, publish at >= 0.80. Unilever: revenue 0.855,
  operating profit 0.905, unlabelled current-assets subtotal 0.815 (only because its section sum passes).
- Engines that read different cells give null + `parser_disagreement` (tested with a perturbed engine).
  No tie-break in M2.4.
- Liabilities are stored positive; equity keeps its sign.
- `total_debt`: derived sum of four printed lines (engine derived, derived_from); borrowings only +
  `lease_not_separately_presented`; a found-but-null component makes it null; absent components are zero
  only when their section subtotal verified (`assumed_zero`); a face "Financial liabilities" line with no
  borrowings makes it null.
- LLM pointer: port, digit masking, schema (no numeric field) and row validation, FakeProvider. Suggestions
  are review items at 0.70 and never change the pack (byte-equal test). NOT built: a live Anthropic adapter
  (no key; the step records "skipped: no provider configured").

Decisions and findings:
- Ambiguous documents ("other", e.g. a statement with no revenue row) use the corporate alias map, since
  values stay anchored and checked; ratios are withheld in M3. Bank/NHS need their maps (M8.1) and list
  every required item as an explicit null meanwhile.
- The rounding tolerance (0.5 x n x unit) means a subtotal off by 1 on a 4-figure sum still passes. That is
  the documented EXTRACTION 5.2 rule; it is not tightened.
- A memo line between two chain anchors (an "Adjusted operating profit" row between revenue and operating
  profit) makes the chain check fail and both figures null: cautious, tested, and documented.
- Import cycle fixed: cached text-layer loader moved to finintel/parse/cached.py.
- Golden excerpt (OQ-10 = A): tests/golden/company_a/excerpt.pdf, 99 KB; regenerate with
  `python scripts/make_golden_excerpt.py company_a 141 143 195 197`.

Not yet done / carried to M2.5:
- Azure DI normalisation and cross-family voting; tau calibration (EVAL 6.1); `reduced_verification` is
  always raised until then.
- company_name is null (not confidently read from the statements).
- Pending from M2.3: tech-lead ADR-010 review of the six new synthetic specs.

---

## M2.3 — 2026-09-29 — green

M2.3 green. company_a: EUR x 1,000,000; FY2024 ends 2024-12-31, FY2023 ends 2023-12-31 (both equal
the labels), on both engines. Lloyds: GBP £m, same dates. Next M2.4 (blocked on the label update below).

| Command | Result |
|---|---|
| `make ci` | exit 0: **599 passed, 0 skipped** |
| `uv run python scripts/gate.py M2.3` | exit 0: status ok; EUR x 1000000; FY2024, FY2023 dates match; FY2022 printed, not labelled |
| `uv run python scripts/gate.py M2.1` / `M2.2` | exit 0 (7/7; 20/20 per engine) |
| `uv run pytest tests/tables/test_headers.py` | 12 specs x 2 engines: status, currency, scale, period ids, end dates, restatement, usable columns |
| `uv run pytest tests/tables/test_header_rules.py` | every SCHEMA 7 token; date rules below |

Rules as implemented (SCHEMA 7-8):
- One distinct unit token per statement (header band or title block); none or two block with
  `needs_unit_confirmation`; income statement and balance sheet must agree. "$" alone blocks with
  `currency_ambiguous` unless the report states a US dollar presentation currency.
- Day and month from the title block, year from the column. "Year ended 31 March 2025" also dates
  the 2024 column. "52 weeks ended", "period ended" and "as at 29 March 2025" never date a
  comparative (a 52/53-week year end shifts by days): that end date stays null unless printed.
- Year headers centred over a column group apply to the whole group; a phrase right-aligned with one
  column is that column's own ("Restated").
- Columnar income statements: one Total/Statutory column per period, or the period's figures stay
  null (`period_ambiguous`). Company columns are excluded with their reason; only Group feeds v1.

Bugs found by the new specs, now tested:
- "£000" parsed as the number 0: a unit row would have become an unlabelled row worth 0.
  Currency + "000"/"'000" is a unit, never a figure.
- A subtitle with a year ("For the year ended 30 June 2025") was swallowed into the header band, and
  a sub-header row ("Restated") cut the band short. Header rows are now found by position: rows
  above the first figure that sit over the figure columns.
- Sparse note references (one or two rows) are invisible to text-strategy grids and were merged into
  labels. When the engine finds no note column but a "Note(s)" header is printed, references under
  it are read from the text layer.

Pending (tech lead): ADR-010 review of the six new M2.3 spec files and the header expectations
added to the older six. Committed so the work is safe; amend if any figure is wrong.

Blocking M2.4 (tech lead): `fixtures/expected/company_a.json` and `company_a.ratios.json` still carry
the pre-decision `total_debt` (all financial liabilities, 32,053 / 29,622) and D/E 1.4211 / 1.4266.
Under the strict rule decided on 2026-09-29 they should expect `total_debt` null (with a warning) and
D/E null with `reason: missing_input`. Code never edits expected files.

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
