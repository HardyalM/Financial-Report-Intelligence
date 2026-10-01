# MILESTONES — session checklist with binary gates

**Rules:**
- **One row = one Claude Code session.** Paste the matching prompt from `prompts/03_MILESTONE_PROMPTS.md`, then add: *"Sub-milestone Mx.y only. Follow CLAUDE.md and docs/MILESTONES.md §Mx.y. Do not skip ahead."*
- Every session begins with its **Read first** list and ends at its **Gate**.
- A gate item is either a **command with a stated pass condition** or a **yes/no tech-lead sign-off**. Nothing reads "looks good".
- If any gate item fails, the session is not done. Use the recovery prompt in `prompts/03_MILESTONE_PROMPTS.md`.

**Re-sized at review:** the draft's M2, M4, M5, M6, M7 and M8 were each larger than one session. The count is now 19 sessions, plus 2 optional (M2.6, M8.2).

---

## Standard gate (every session, in addition to its own gate)

These checks are created in M0 and run in CI.

| # | Check | Pass condition |
|---|---|---|
| G1 | `make lint typecheck test contracts-check` | exit 0 |
| G2 | `python scripts/check_scope.py <session-id>` | exit 0: every changed path is in that session's **allowed paths** (defined in `scripts/scope.yaml`, generated from this file at M0) **or** in the global allow-list that every session may touch: `docs/MILESTONES.md` (ticking boxes), `docs/STATUS.md` (session log: commands and results), `pyproject.toml` and `uv.lock` (adding a dependency the session needs), `.python-version`, `Makefile`, `.env.example`, `tests/**`. *(Global list added at M0: without it G2 and G6 contradicted each other, and no later session could add a dependency. `docs/STATUS.md` added 2026-09-26 at the tech lead's request.)* |
| G3 | `git diff --name-only main...HEAD -- fixtures/expected` | empty (Claude Code never edits expected files) |
| G4 | `git diff --quiet main...HEAD -- CLAUDE.md` | exit 0 (only the tech lead edits `CLAUDE.md`) |
| G5 | `python scripts/check_scope.py --web-guard` | exit 0: `web/` does not exist unless tag `m3-done` exists |
| G6 | This file | the session's boxes are ticked in the same commit |

**Eval report contract** (used by the gates below). `make eval-* COMPANY=x` writes `artifacts/eval/latest/report.json` with at least these fields:
- `e1.labelled`, `e1.matched`, `e1.honest_null`, `e1.silent_wrong`, `e1.unit_errors`
- `e2.expected`, `e2.matched`
- `e3.hit_at_8`
- `e4.displayed_unverified_citations`, `e4.displayed_naked_numbers`, `e4.displayed_advice`
- `e6.published_llm_pointer`, `e6.published_vision_only`
- `e7.cells`, `e7.matched`
- `e8.risk_recall`, `e8.kam_recall`, `e8.going_concern_correct`
- `qa.passed`, `qa.total`.

`python scripts/gate.py <session-id>` reads it and exits 0 only if that session's conditions hold.

---

## Pre-flight (before M0)

- [ ] Git repository initialised and the pack committed (`git log --oneline | wc -l` ≥ 1).
- [ ] OQ-2 and OQ-3 decisions written in `docs/OPEN_QUESTIONS.md` (the "Decision:" lines are not blank).
- [ ] Spend caps set on every API account. *(Sign-off: yes/no.)*
- [ ] `fixtures/pdfs/company_a.pdf` and `company_b.pdf` exist; `fixtures/pdfs/SOURCES.md` has one filled row for each.
- [ ] `fixtures/expected/company_a.json` labelled (PLAN §7.2). The M1 gate reads its page count; M2.1 onwards check every cell.

## Which decision blocks which session

| Open question | Must be answered before |
|---|---|
| OQ-2, OQ-3 (schema v1.1.0) | M0 |
| OQ-7 (premium parse scope) | M1 |
| OQ-9 (LLM provider), OQ-10 (golden excerpts) | M2.4 |
| OQ-6 (ESEF check, option B) | M2.5 |
| OQ-1 (ROCE), OQ-11 (equity basis) | M3 |
| OQ-8 (hosting: A for v1) | M6.2 |
| OQ-4 (bank ratios), OQ-5 (NHS, only if used) | M8.1 |

---

## M0 — Repository contract

**Read first:** `CLAUDE.md`; PLAN §4–5; ARCHITECTURE §2 and §5; SCHEMA §1 and §9.
**Allowed paths:** `pyproject.toml`, `Makefile`, `finintel/**`, `tests/**`, `scripts/**`, `.github/workflows/**`, `.env.example`, `README.md`, `schemas/statement_pack.schema.json` (only if OQ-2/3 approved).

- [x] pyproject (Python 3.12, ruff, mypy **strict everywhere**), pytest, hypothesis. *Network blocking is a test fixture (`tests/conftest.py`) instead of pytest-socket: one dependency fewer, same gate.*
- [x] Package skeleton per ARCHITECTURE §2; typed stubs raising `NotImplementedError` that name their session.
- [x] Contracts generated from the schema by `scripts/gen_contracts.py` (standard library plus `ruff format`; *replaces datamodel-code-generator so generation runs offline and in CI*); `make contracts-check` detects drift.
- [x] `scripts/scope.yaml` (generated from this file by `scripts/gen_scope.py`), `scripts/check_scope.py`, `scripts/check_imports.py`, `scripts/gate.py`; G1, G2–G5 wired into CI.
- [x] `.env.example` (names only); a `README.md` stub pointing to `docs/PLAN.md`.
- [x] OQ-2/3 = yes: schema v1.1.0 applied; `EXAMPLE_company_a.json` validates as 1.0.0 and as 1.1.0.

**Gate:**
- [x] G1–G6 pass. *2026-09-26: `uv lock && make ci` exit 0 on CPython 3.12.14 (macOS arm64): ruff, strict mypy, 66 tests, contract drift, scope file, web guard; `check_scope.py M0 --base main` exit 0. See docs/STATUS.md.*
- [x] `pytest tests/test_smoke.py` passes: the schema loads and `EXAMPLE_company_a.json` validates.
- [x] `pytest tests/test_no_network.py` passes: opening a socket raises.
- [x] `python scripts/check_imports.py --forbid fitz,pdfplumber,httpx,anthropic,voyageai` exits 0 (no parsing or LLM code yet).
- [x] CI run for the commit is green (or `make ci` exits 0 if there is no remote yet). *No remote: `make ci` exit 0 with `uv.lock` committed.*
- [ ] *Sign-off:* package layout matches ARCHITECTURE §2 (yes/no).

---

## M1 — PDF inspection toolkit

**Read first:** EXTRACTION §0–1; ADR-001; COST_AND_OPS §1; OQ-7.
**Allowed paths:** `finintel/ingest/**`, `finintel/parse/text_layer*`, `finintel/parse/engines/pdfplumber*`, `finintel/parse/engines/azure_di*` (raw call and storage only), `finintel/cache/**`, `finintel/cli/**`, `tests/**`.

- [x] `finintel inspect <pdf>` writes `artifacts/inspect/{stem}/summary.json`, `pages.jsonl`, `text/`, `tables/` and thumbnails of keyword pages. *(Also `outline.json`, and `tables/*.txt` for reading.)*
- [x] Azure DI raw call if a key exists; otherwise `parser_skipped: ["azure_di"]`. *(A failed call is `parser_failed`, is never cached, and the run continues on the local engines.)*
- [x] Content-addressed cache.
- [x] The inspector's glob covers `fixtures/pdfs/` **only** (never `fixtures/holdout/`). *(Explicit holdout paths, directories and symlinks into it are refused with exit 3.)*

**Gate:**
- [x] G1–G6 pass. *2026-09-29: `make ci` exit 0 (213 passed, 0 skipped, fixture PDFs included); `check_scope.py M1 --base m0` exit 0.*
- [x] `finintel inspect fixtures/pdfs/company_a.pdf` and the same for `company_b.pdf` both exit 0. *Cold: 9.8 s (305 pp.) and 12.7 s (338 pp.).*
- [x] `summary.json.page_count` equals `source.page_count` in `fixtures/expected/company_a.json`. *305 = 305; also asserted by `tests/inspect/test_fixture_pdfs.py`.*
- [x] A second run prints `vendor_calls=0`. *Both PDFs; text layer and all 20 pdfplumber pages from cache.*
- [x] Either `summary.json.parser_skipped` contains `azure_di`, or `azure/raw.json` exists. *`parser_skipped: ["azure_di"]` (no key) for both.*
- [x] `pytest tests/inspect -k "holdout"` passes: a test asserts that `fixtures/holdout/` is excluded. *13 passed.*
- [ ] *Sign-off:* the income statement and balance sheet pages appear among the top 10 keyword-hit pages of `pages.jsonl` (yes/no). *Evidence: company_a p.143 rank 2, p.141 rank 3 (company balance sheet p.197 rank 1); company_b p.218 rank 1, p.216 rank 2.*

---

## M2.1 — Locate statements and profile the document

**Read first:** EXTRACTION §1 (including §1.4); SCHEMA §4; ADR-010.
**Allowed paths:** `finintel/locate/**`, `evals/synthetic/**`, `tests/**`, `evals/__init__.py`, `finintel/cli/**`, `finintel/parse/text_layer*`, `scripts/gate.py`, `scripts/scope.yaml`.
*Amended 2026-09-29 in the M2.1 session. The gate below runs the finintel locate command (finintel/cli) and the scripted M2.1 check in scripts/gate.py, which the original list did not allow; evals/__init__.py makes the synthetic generator importable; the text-layer change fixes an M1 bug found here (page size reported in rotated space while word coordinates are unrotated).*

- [x] Page scorer, title scope classifier, hard exclusions, continuation and spread detection. *(Also: chrome filter for navigation bars, printed-folio inference, contents-page hints.)*
- [x] `DocumentProfile`: document type and classified-balance-sheet test.
- [x] Synthetic generator plus the first specs: company page before group page; liquidity-ordered balance sheet; two-page balance sheet. *(Plus a bank spec. Spec figures reviewed and approved by the tech lead 2026-09-29, ADR-010.)*

**Gate:**
- [x] G1–G6 pass. *2026-09-29: `make ci` exit 0 (330 passed); `check_scope.py M2.1 --base m1` exit 0.*
- [x] `python scripts/gate.py M2.1` exits 0 (7/7 PASS). It checks that:
  - `finintel locate company_a --json` gives income statement and balance sheet pages equal to the `page` values in `company_a.json`
  - at least one `scope=company` page is detected and not selected
  - `document_type == "corporate"` and `balance_sheet_classified == true`.
- [x] `finintel locate company_b --json` gives `document_type == "bank"` and `balance_sheet_classified == false`.
- [x] The three synthetic specs pass. *(Four: `tests/locate/test_synthetic_specs.py`.)*

---

## M2.2 — Table model (text-layer family)

**Read first:** EXTRACTION §2, §3 (notes column) and §4.1–4.2.
**Allowed paths:** `finintel/parse/engines/pdfplumber*`, `finintel/parse/engines/pymupdf_tables*`, `finintel/tables/**`, `evals/synthetic/**`, `tests/**`, `finintel/parse/engines/base.py`, `finintel/locate/signals.py`, `scripts/gate.py`, `scripts/scope.yaml`.
*Amended 2026-09-29 in the M2.2 session. The engine output contract ParsedTables lives in finintel/parse/engines/base.py, whose stub said its fields are defined in M1 and M2.2, yet no session was allowed to touch it; the gate below needs a scripted M2.2 check in scripts/gate.py; finintel/locate/signals.py gains superscript-aware row grouping (a footnote marker was splitting a Unilever row and losing its figures).*

- [x] `StatementTable` from pdfplumber and PyMuPDF `find_tables`, with rows aligned to text-layer lines, styles, section headers, the notes column excluded, `note_ref` kept, and multi-page merge. *(Engines say where a cell is; its characters come from the text layer, ADR-001.)*
- [x] Number grammar.
- [x] Synthetic specs: notes column; spread page. *(Figures reviewed by the tech lead before commit, ADR-010.)*

**Gate:**
- [x] G1–G6 pass. *2026-09-29: `make ci` exit 0 (488 passed); `check_scope.py M2.2 --base m2.1` exit 0.*
- [x] `python scripts/gate.py M2.2` exits 0: for **every** labelled cell in `company_a.json`, a table cell exists whose normalised `raw_text` equals the label, on the labelled page (prints `N/N`). *20/20 for each engine separately.*
- [x] Number-grammar tests pass: a dash gives 0; "n/a" stays unparsed (not 0); brackets give a negative; footnote markers are stripped.
- [x] No value column has a "Note(s)" header (test). *(`tests/tables/test_specs.py`, all specs, both engines.)*

---

## M2.3 — Header semantics

**Read first:** EXTRACTION §3; SCHEMA §7–8.
**Allowed paths:** `finintel/tables/**`, `evals/synthetic/**`, `tests/**`, `scripts/gate.py`, `scripts/scope.yaml`.
*Amended 2026-09-29 in the M2.3 session: the gate below needs the scripted M2.3 check in scripts/gate.py.*

- [x] Unit and currency (blocking), period columns, restatement markers, statutory column in columnar income statements, entity-column scope.

**Gate:**
- [x] G1–G6 pass. *2026-09-29: `make ci` exit 0; `check_scope.py M2.3 --base m2.2` exit 0 (see docs/STATUS.md for counts).*
- [x] `python scripts/gate.py M2.3` exits 0: `company_a` unit scale, currency, period ids and end dates equal `company_a.json`. *EUR x 1,000,000; FY2024 2024-12-31, FY2023 2023-12-31, both engines; FY2022 printed, not labelled.*
- [x] These synthetic specs pass (`tests/tables/test_headers.py`, both engines; ADR-010 review of the new spec figures still pending with the tech lead):
  - £000
  - £m
  - missing unit (status `needs_unit_confirmation`)
  - bare `$` (`currency_ambiguous`)
  - restated header
  - columnar income statement (Total column chosen)
  - Group | Company columns (only Group used).

---

## M2.4 — Deterministic mapping and pack (local engines)

**Read first:** EXTRACTION §4.3–4.4, §5.2–5.4a; SCHEMA §5–6; ADR-005; ADR-007; OQ-9; OQ-10.
**Allowed paths:** `finintel/mapping/**`, `finintel/reconcile/**`, `finintel/llm/**`, `tests/**`, `tests/golden/**` (if OQ-10 = A), `finintel/extract.py`, `finintel/evals/**`, `finintel/cli/**`, `finintel/parse/cached.py`, `scripts/gate.py`, `scripts/make_golden_excerpt.py`, `scripts/scope.yaml`.
*Amended 2026-09-30 in the M2.4 session: the gate runs `make eval-e1` (finintel/cli, finintel/evals) over a pipeline entry point (finintel/extract.py); the cached text-layer loader moved to finintel/parse/cached.py to break an import cycle; the golden excerpt needs its generator script.*

- [x] Corporate alias map; structural rules; exclusions; arithmetic checks; confidence; τ; `total_debt` presence rule; pack emission. *(Bank and NHS alias maps are M8.1: until then those types list every required item as an explicit null.)*
- [x] Number-blind LLM pointer → review items only; `fake` provider in tests. *(Port, masking, schema and row validation only. The live Anthropic adapter is not built: no key exists, and the pointer step is recorded as skipped.)*

**Gate:**
- [x] G1–G6 pass. *2026-09-30: `make ci` exit 0 (646 passed); `check_scope.py M2.4 --base m2.3` exit 0.*
- [x] `make eval-e1 COMPANY=company_a ENGINES=local` followed by `python scripts/gate.py M2.4` exits 0, requiring: *(22/22 matched; 0 silent wrong)*
  - `e1.matched == e1.labelled`
  - `e1.silent_wrong == 0`
  - `e1.unit_errors == 0`
  - `e6.published_llm_pointer == 0`.
- [x] Negative test: with the revenue row removed, `revenue.value is null` and a `missing_item` warning exists.
- [x] A scripted LLM returning a numeric field is rejected at schema validation (test).
- [x] `total_debt` presence tests pass: lease present but null gives null; absent with a passing subtotal gives `assumed_zero`; absent with a failing subtotal gives null.
- [x] The emitted pack validates against the schema.
- [x] If OQ-10 = A: `tests/golden/company_a/` is committed and E1 runs inside `make test`. *(99 KB excerpt: pages 141, 143, 195, 197 at their original page numbers, others blank.)*

---

## M2.5 — Cross-family reconciliation

**Read first:** EXTRACTION §5 (all); ADR-001; OQ-6.
**Allowed paths:** `finintel/parse/engines/azure_di*`, `finintel/reconcile/**`, `finintel/tables/**`, `tests/**`, `docs/EXTRACTION.md` (§5.3 calibration note only), `finintel/extract.py`, `finintel/cli/**`, `scripts/gate.py`, `scripts/scope.yaml`.
*Amended 2026-10-01 in the M2.5 session: the pipeline entry point and CLI gain `--engines all` (finintel/extract.py, finintel/cli/**), and the gate needs an `azure.ran` condition in scripts/gate.py.*

- [x] Azure DI normalised into `StatementTable`; anchoring; row, column and period re-derived from the text layer; family voting; `ExtractionReport`; review items. *(Built and tested against an Azure-shaped stand-in; never run on a real Azure response.)*
- [ ] τ calibration (EVAL §6.1). *Local-family evidence recorded; real two-family calibration needs an Azure key.*
- [ ] If OQ-6 = B: ESEF label check run, with results added to the labelling notes by the tech lead.

**Gate:**
- [x] G1–G6 pass. *2026-10-01: `make ci` exit 0 (656 passed); `check_scope.py M2.5 --base m2.4` exit 0.*
- [ ] `make eval-e1 COMPANY=company_a ENGINES=all` followed by `python scripts/gate.py M2.5` exits 0 (`matched == labelled`, `silent_wrong == 0`). ***BLOCKED: needs an Azure DI key. Without one the gate fails on `azure.ran == True`, by design.***
- [x] Test: every published value has `ExtractionReport.row_source == "text_layer"`.
- [x] Test: a perturbed engine value gives null or a resolved `parser_disagreement`, never a silent pick.
- [x] Test: a scripted engine returning a "corrected" number produces an `unanchored_candidate` and nothing is published from it.
- [x] With the Azure key unset: `silent_wrong == 0` and the pack contains a `reduced_verification` warning.
- [x] `git diff main...HEAD -- docs/EXTRACTION.md` shows the §5.3 calibration note (or an explicit "τ unchanged, evidence: …"). *(Says calibration on the second family is pending.)*
- [ ] *Sign-off:* you agree with the decision in one disputed cell's `ExtractionReport` (yes/no).

## M2.6 — Vision family *(optional)*

**Run only if** the M2.5 report lists at least one golden cell left null by an unresolved disagreement, **or** you opt in.
**Read first:** EXTRACTION §5.1, §5.1a, §5.4.
**Allowed paths:** `finintel/parse/engines/vision*`, `finintel/reconcile/**`, `tests/**`.

**Gate:**
- [ ] G1–G6 pass.
- [ ] `e6.published_vision_only == 0`.
- [ ] Corroboration test (vision on the same cell raises the agreement count) and tripwire test (vision on a different cell caps confidence at 0.79 and creates a review item) pass.
- [ ] `e1.matched` is unchanged from M2.5.

---

## M3 — Deterministic ratios

**Read first:** `CLAUDE.md` (locked formulas); SCHEMA §11; ADR-008; OQ-1; OQ-11.
**Allowed paths:** `finintel/ratios/**`, `schemas/ratio_pack.schema.json`, `finintel/contracts/**`, `tests/**`, `finintel/evals/**`, `finintel/cli/**`, `scripts/gen_contracts.py`, `scripts/scope.yaml`.
*Amended 2026-10-01 in the M3 session: `make eval-e2` needs the E2 comparison (finintel/evals) and a CLI command, and the contract generator lists the new schema.*

- [x] `RatioPack` schema and contract; pure `compute_ratios`; `reason` exactly as `CLAUDE.md` specifies; `applicability`; flags beside values; changes.

**Gate:**
- [x] G1–G6 pass. *2026-10-01: see docs/STATUS.md for counts; `check_scope.py M3 --base m2.5` exit 0.*
- [x] `make eval-e2 COMPANY=company_a` followed by `python scripts/gate.py M3` exits 0 *(8/8, from the labelled pack and from the pipeline's pack)*: `e2.matched == e2.expected` for **both** periods at 1e-9.
  - If `company_a.ratios.json` is missing, the session prints the computed values and G3 still passes, because no expected file was created.
- [x] **Drift test:** the formula strings in `RatioPack` equal the strings parsed from `CLAUDE.md` (test reads `CLAUDE.md`).
- [x] Hypothesis property test (≥ 200 examples; 300 run): multiplying every input by 1,000 leaves every ratio unchanged.
- [x] Synthetic bank pack: all four ratios have `value: null`, `reason: "missing_input"` and `applicability: "not_applicable"`.
- [x] Negative-equity test: the value is present **and** the flag `negative_denominator` is set.

---

## M4.1 — Section tree and chunker (no database)

**Read first:** RAG §1–2; ADR-002.
**Allowed paths:** `finintel/narrative/**`, `evals/synthetic/**`, `tests/**`, `finintel/cli/**`, `finintel/parse/ruled_tables.py`, `scripts/gate.py`, `scripts/scope.yaml`.
*Amended 2026-10-01 in the M4.1 session: the PyMuPDF ruled-table finder lives in finintel/parse/ruled_tables.py (the import boundary keeps PyMuPDF in parse/); the gate runs `finintel chunks` (finintel/cli) and a scripted audit in scripts/gate.py. The synthetic PDFs for the T18 and note tests are built in tests/narrative rather than evals/synthetic: they need no spec files or tech-lead figures.*

- [x] Section tree; header and footer removal; reading order; **table-region detection on every narrative page**; chunking; char→page map; note state machine; footnotes; `chunker_version` in `chunk_id`. *(Section tree from bookmarks plus in-page headings. The printed-contents-page and running-header sources are not used: both goldens have bookmarks.)*

**Gate:**
- [x] G1–G6 pass. *2026-10-01: see docs/STATUS.md; `check_scope.py M4.1 --base m3` exit 0.*
- [x] `finintel chunks fixtures/pdfs/company_a.pdf --json` exits 0, and `python scripts/gate.py M4.1` confirms:
  - 0 chunks without `page_start`
  - 0 chunks in `primary_statements` or `company_statements`
  - 0 prose chunks overlapping a table region.
- [x] Tests pass:
  - a quote either side of a page-crossing chunk gets the correct page
  - a note spanning two pages keeps its `note_number`
  - changing `chunker_version` changes `chunk_id`
  - a synthetic KPI-table page yields no prose chunk containing table text (T18).
- [ ] *Sign-off:* 10 random chunks have correct `heading_path` values (yes/no).

## M4.2 — Index and retrieval

**Read first:** RAG §3; ARCHITECTURE §2.1; COST_AND_OPS §2.
**Allowed paths:** `finintel/db/**`, `finintel/retrieval/**`, `migrations/**`, `docker-compose.yml`, `tests/**`, `finintel/evals/e3.py`, `finintel/cli/**`, `scripts/scope.yaml`.
*Amended 2026-10-01 in the M4.2 session: the gate runs `finintel eval-e3` (finintel/cli, finintel/evals/e3.py). The labels file is read-only to Claude; `--labels` reads it from another path without copying it.*

- [ ] Docker Postgres; migrations for `documents`, `chunks`, `chunk_embeddings`; FTS; embeddings (Voyage, local, fake); HNSW; RRF; rerank; priors; floor; topic query sets including bank and NHS variants.

**Gate:**
- [ ] G1–G6 pass.
- [ ] `docker compose up -d db && make migrate` exits 0.
- [ ] `make eval-e3 COMPANY=company_a` followed by `python scripts/gate.py M4.2` exits 0: `e3.hit_at_8 >= 0.8`. The report records which embedding model was used.
  - If `company_a.retrieval.json` is missing, the session **prints** the file format in its output (it never writes into `fixtures/expected/`) and stops. G3 passes.
- [ ] Test: query variants are selected by `document_type`.
- [ ] *Sign-off:* the top 8 for "principal risks" are on-topic (yes/no).

---

## M5.1 — Commentary contracts and validators (no LLM)

**Read first:** RAG §4–6; ADR-003; ADR-005.
**Allowed paths:** `finintel/commentary/validators/**`, `finintel/commentary/render/**`, `schemas/citation.schema.json`, `schemas/commentary.schema.json`, `finintel/contracts/**`, `tests/**`.

**Gate:**
- [ ] G1–G6 pass.
- [ ] `pytest tests/commentary -q` passes, including **T1–T18** (scripted outputs; the network is blocked).
- [ ] Renderer tests pass for £m, £000 and $m scales, percentages, percentage-point changes and null rendering.

## M5.2 — Commentary generation

**Read first:** RAG §3.4, §4; EVAL §3.4, §3.6, §4.
**Allowed paths:** `finintel/commentary/**`, `finintel/llm/**`, `tests/**`.

**Gate:**
- [ ] G1–G6 pass.
- [ ] `make eval-live COMPANY=company_a STAGE=commentary` exits 0 and writes `artifacts/commentary/company_a.json`.
- [ ] `python scripts/gate.py M5.2` exits 0, requiring:
  - `e4.displayed_unverified_citations == 0`
  - `e4.displayed_naked_numbers == 0`
  - `e4.displayed_advice == 0`
  - `e8.risk_recall >= 0.8`, `e8.kam_recall >= 0.8`, `e8.going_concern_correct == true`
  - `qa.passed >= 17` (with `qa.total == 20`).
- [ ] With the LLM key unset, the run exits 0 and the output is labelled `extractive`.
- [ ] Replaying the recorded run offline reproduces a byte-identical `output`.
- [ ] `ratings.json` is complete: supported ≥ 90 %, contradicted = 0. *(You rate; the check is arithmetic.)*

---

## M6.1 — Worker and persistence

**Read first:** ARCHITECTURE §2.1, §4; COST_AND_OPS §3.
**Allowed paths:** `finintel/worker/**`, `finintel/db/**`, `migrations/**`, `finintel/cli/**`, `tests/**`.

**Gate:**
- [ ] G1–G6 pass.
- [ ] A migration test confirms every table and column in ARCHITECTURE §2.1 exists.
- [ ] `finintel run fixtures/pdfs/company_a.pdf` ends with document status `ready`, and the stored `pack_sha` equals the file pipeline's pack hash.
- [ ] Injected worker crash mid-run, then restart: the run completes and no stage executes twice (test).
- [ ] Injected Azure failure: the run completes on the fallback, with `reduced_verification: true`.

## M6.2 — HTTP API

**Read first:** EXTRACTION §6; ADR-004; OQ-8.
**Allowed paths:** `finintel/api/**`, `schemas/openapi.json`, `tests/**`.

**Gate:**
- [ ] G1–G6 pass.
- [ ] API tests pass for every endpoint in EXTRACTION §6, plus uploads, report, commentary and pages.
- [ ] Tests:
  - an override recomputes ratios and sets `stale == true`
  - an unanchored `set_value` gives 422; forced, it gives 200 plus `human_override_unanchored`
  - a duplicate upload returns the same id
  - a synthetic unit-ambiguous report stays `needs_unit_confirmation` until confirmed
  - the statement-location and document-type endpoints re-run the affected stages.
- [ ] `schemas/openapi.json` is exported and `make contracts-check` covers it.

---

## M7.1 — Report screen (read-only)

**Read first:** [UI.md](UI.md) §1–5; RAG §4.3.
**Allowed paths:** `web/**`, `tests/e2e/**`.

**Gate:**
- [ ] G1–G6 pass (tag `m3-done` exists, so `web/` is allowed).
- [ ] Playwright: the report screen renders `company_a` from a precomputed API fixture.
- [ ] Playwright: **every row state in UI.md §4** and **every ratio-card state in UI.md §5** renders from the fixture packs (one test per state).
- [ ] `node scripts/check-deps.js` exits 0: no charting library in `web/package.json`.
- [ ] Playwright: the footer text "Research aid. Not investment advice." is present.

## M7.2 — Evidence panel and commentary

**Read first:** UI.md §6–7; RAG §5.
**Allowed paths:** `web/**`, `tests/e2e/**`.

**Gate:**
- [ ] G1–G6 pass.
- [ ] Playwright clicks **every** citation on `company_a`. For each, the viewer's page equals `citation.page` and at least one highlight box is visible.
- [ ] Playwright clicks every page chip. The provenance panel shows the engine families and checks.
- [ ] Topic states (`ok`, `insufficient_evidence`, `validation_failed`, extractive, stale) each render from fixtures.

## M7.3 — Upload, progress and review

**Read first:** UI.md §3, §6.3; EXTRACTION §6.
**Allowed paths:** `web/**`, `tests/e2e/**`.

**Gate:**
- [ ] G1–G6 pass.
- [ ] Playwright end to end: a small synthetic PDF moves through the progress stages to `ready`.
- [ ] Playwright: accepting a candidate shows the value with a "Confirmed by you" badge.
- [ ] Playwright: entering a value not on the page shows the refusal message, and nothing is saved.
- [ ] Playwright: after an override, the stale-commentary banner appears.
- [ ] Playwright: the unit-confirmation and point-to-page flows complete on synthetic fixtures.

---

## M8.1 — Bank support

**Read first:** EXTRACTION §1.4, §7; SCHEMA §9 (bank ids); OQ-4; OQ-5.
**Allowed paths:** `finintel/mapping/aliases/bank.yaml`, `finintel/mapping/**`, `finintel/locate/**`, `web/**`, `tests/**`.

**Gate:**
- [ ] G1–G6 pass; `fixtures/expected/company_b.json` exists (you labelled it).
- [ ] `make eval-e1 COMPANY=company_b` followed by `python scripts/gate.py M8.1` exits 0, requiring:
  - `e1.matched + e1.honest_null == e1.labelled`
  - `e1.silent_wrong == 0`
  - all four corporate ratios have `applicability == "not_applicable"`.
- [ ] `make eval COMPANY=company_a`: E1 and E2 are unchanged (`matched == labelled`).
- [ ] Playwright: the bank report shows "Not applicable to banks" on all four ratio cards.

## M8.2 — Bank ratios and reported metrics *(only if OQ-4 = B)*

**Read first:** OQ-4; SCHEMA §11 (`ReportedMetric`).
**Allowed paths:** `finintel/ratios/**`, `finintel/commentary/**`, `schemas/reported_metric.schema.json`, `finintel/contracts/**`, `web/**`, `tests/**`.

**Gate:**
- [ ] G1–G6 pass.
- [ ] `CLAUDE.md` contains the two bank ratio formulas (added by you), and the drift test passes for them.
- [ ] `e2` matches `company_b.ratios.json`.
- [ ] Test: every `ReportedMetric.value_text` is a substring of its verified quote.
- [ ] Test: no `RatioPack` input references a reported metric.

## M8.3 — Honesty layer

**Read first:** EVAL §1, §4; PLAN §6; INTERVIEW.md.
**Allowed paths:** `docs/RESULTS.md`, `docs/INTERVIEW.md`, `README.md`, `web/**`, `tests/**`.

**Gate:**
- [ ] G1–G6 pass.
- [ ] Held-out run: `company_c` moved from `fixtures/holdout/` and labelled by you; `make eval COMPANY=company_c` run **once**; its `run_id` recorded in `RESULTS.md`.
- [ ] `python scripts/check_results.py` exits 0: every number in `docs/RESULTS.md` equals a field in a cited eval `report.json`.
- [ ] Playwright: the limitations page is reachable from the report screen.
- [ ] `README.md` contains the architecture diagram, a "What fails" section and local-run steps.
- [ ] Fresh-clone test: `git clone` into a temporary directory, then `make dev` with **no API keys**, completes `company_a` (exit 0).
- [ ] *Sign-off:* you would say every sentence in `RESULTS.md` in an interview (yes/no).

---

## Definition of v1 done

All items in `prompts/04_QUALITY_BAR.md` are true; every gate above is ticked (optional sessions excepted); and you can answer the questions in [INTERVIEW.md](INTERVIEW.md) §3 without notes.
