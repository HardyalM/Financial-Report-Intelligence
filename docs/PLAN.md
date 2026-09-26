# PLAN — Financial Report Intelligence & RAG

Status: **draft for tech-lead approval**. No application code exists or will be written until this plan is approved.

Companion documents: [ARCHITECTURE](ARCHITECTURE.md) · [SCHEMA](SCHEMA.md) · [EXTRACTION](EXTRACTION.md) · [RAG](RAG.md) · [EVAL](EVAL.md) · [RISKS](RISKS.md) · [COST_AND_OPS](COST_AND_OPS.md) · [MILESTONES](MILESTONES.md) · [OPEN_QUESTIONS](OPEN_QUESTIONS.md)

---

## 0. Repository state at planning time

| Item | State | Consequence |
|---|---|---|
| `CLAUDE.md` | Present, read | Governs every session. Locked ratio definitions are reproduced verbatim in this plan. |
| `schemas/statement_pack.schema.json` | Present, v1.0.0 | Usable. Gaps identified; a backwards-compatible v1.1.0 is **proposed** in [SCHEMA §9](SCHEMA.md#9-proposed-v110-extension-backwards-compatible), not applied. |
| `fixtures/pdfs/` | **Empty** (only `SOURCES.md`) | Blocks M1 exit and all of M2 onwards. |
| `docs/UI.md`, `docs/INTERVIEW.md` | Written at plan review | M7.1 can start once the plan is approved |
| `fixtures/expected/` | Only `EXAMPLE_*` files (fictional numbers) | Blocks the M1 gate (page count) and everything from M2.1. See [§7 Blocked on fixtures](#7-blocked-on-fixtures). |
| Git | Not yet initialised | Blocks M0 (CI needs a repo). |

The plan below is written so that none of this blocks planning, and so that the labelling work in §7 is unaffected by the open accounting decisions (we label a superset).

---

## 1. Problem framing

Credit analysts, equity researchers, commercial bankers and public-sector finance teams read 150–350-page annual reports to extract a handful of figures and a few paragraphs of judgement. The work is slow, and the two usual shortcuts are both unreliable:

- **Copy-paste into a spreadsheet**: slow, error-prone around units, signs and group-vs-company statements.
- **Ask a chatbot**: fast, fluent and untrustworthy. LLMs round, re-scale, pick adjusted figures over statutory ones, and invent plausible numbers.

**This product separates the two jobs.**

1. **Numbers** are extracted from the primary statements into a typed `StatementPack`, reconciled across independent parsing engines, anchored to the PDF text layer, checked arithmetically, and turned into ratios by pure Python. An LLM may *point at* a row; it never supplies a number.
2. **Narrative** is retrieved from the report with page-aware chunking and summarised by an LLM that must cite a verbatim quote for every claim. Code verifies each quote, re-derives each page number, and rejects any number that is not injected from the packs or copied verbatim from a cited quote.

The v1 promise is deliberately narrow: **excellent on 2–3 labelled reports, designed to extend, honest when it fails.** When the system is not sure, it shows a null with a reason, never a confident wrong figure.

### 1.1 Non-goals

| Horizon | In scope | Explicitly out of scope |
|---|---|---|
| **v1** | Digitally born UK annual reports; consolidated income statement and balance sheet; four locked ratios for two periods; grounded commentary on four topics; human review of extracted cells; **one-screen** analyst dashboard ([UI.md](UI.md)); eval harness on 2–3 goldens plus a synthetic layout suite; **runs locally** | Accuracy claims on arbitrary uploads; scanned PDFs as a happy path; cash flow statement; segment extraction; multi-report time series; chat or free-form Q&A in the UI; market data, live prices, valuation, peer comparison; investment recommendations; multi-tenant auth; agents. **Removed at review as hidden scope:** hosted deployment; Reducto, LlamaParse and Docling adapters and the parser bake-off; cross-run circuit breaker; charting library; Gemini adapter (unless OQ-9 = B). |
| **v1.1** | Hosted demo (OQ-8); additional parser adapters if a golden shows the need; cash flow items and interest cover; bank-specific ratios (if not taken in v1, see [OQ-4](OPEN_QUESTIONS.md)); NHS trust support as a first-class document type; ESEF/iXBRL runtime verification ([OQ-6](OPEN_QUESTIONS.md)); 3–5-year series from several reports with restatement handling; measured OCR path for scans; segment note extraction | Same as v1 for market data, advice, agents |
| **v2** | US 10-K via SEC XBRL; peer comparison on reconciled packs; saved analyst workspaces; SSO and role-based access; batch API; IFRS 18 layouts (effective 2027, subject to UK endorsement) | Autonomous trading or recommendation features, ever |

### 1.2 Locked v1 ratio definitions (verbatim from `CLAUDE.md`)

| Ratio | Formula |
|---|---|
| Operating margin | `operating_profit / revenue` |
| Current ratio | `current_assets / current_liabilities` |
| Debt-to-equity | `total_debt / total_equity` |
| ROCE | `operating_profit / (total_assets - current_liabilities)` |

- Year-end balances, not averages, in v1.
- `total_debt` (debt-to-equity) = interest-bearing borrowings + lease liabilities if separately present, else borrowings only + a warning.
- `total_equity` includes non-controlling interests.
- A null required input gives a null ratio with reason `missing_input`.

The ROCE definition was changed by the tech lead on 2026-09-26 ([OQ-1](OPEN_QUESTIONS.md) = B), and the equity basis fixed ([OQ-11](OPEN_QUESTIONS.md) = A). Only the tech lead edits `CLAUDE.md`; code never does.

---

## 2. User journeys

The user is an analyst who wants a trustworthy first read of a report in minutes, and who will check anything that matters.

### J1 — Upload

1. Analyst drags in `annual_report.pdf` (≤ 50 MB).
2. System hashes it, stores the original, checks it is digitally born and unencrypted, and starts a job.
3. The UI shows stage progress: *Reading pages → Finding statements → Extracting figures → Checking → Calculating ratios → Indexing narrative → Writing commentary.*

**Failure variants:**
- Encrypted PDF: rejected with a reason.
- Scanned PDF: accepted with a banner. Figures are shown only as review suggestions, never published automatically ([EXTRACTION §0](EXTRACTION.md)).
- Unit ambiguous: extraction pauses with a request to confirm the unit, and cites the pages concerned.

### J2 — Review extraction

1. The analyst sees the income statement and balance sheet items for both periods. Each figure has a **page chip** (click to open the PDF page with the cell highlighted), a **note chip** where the statement gives a note reference, and a verification label ("Two engine families agree", "One engine family", "Manual").
2. **Every unmapped item is visible and explained** (row states in [UI.md §4](UI.md)):
   - **what** is missing
   - **why**, as the warning code in plain English
   - **where we looked**: pages scanned and labels tried
   - **what the analyst can do**: accept a candidate, confirm a model suggestion, enter a value that exists on the page, or point to the statement page.
3. **Model suggestions are shown as suggestions** ("Suggested by model: confirm?") and are never published until a person confirms them.
4. Every override is logged; ratios recompute instantly; commentary is marked stale. Forced or unanchored values and manually confirmed units carry permanent badges.

### J3 — Ratios

Four ratio cards show both periods and the change, the locked formula, and each input with its page. States:
- `ok`
- **null**: "Needs current liabilities: not found", with a link to that row
- **not applicable**: "Not applicable to banks: the balance sheet has no current/non-current split"
- **withheld**: "Document type unclear: confirm to show ratios".

Flags such as negative equity appear **beside** the value, never instead of it. Period-on-period changes are computed in code.

### J4 — Commentary

Four topic panels:

- Revenue drivers
- Strategic risks
- Governance and directors' notes
- Liquidity and capital (only if evidenced)

A numbers snapshot is rendered from templates, not written by the LLM. Topics with thin evidence say so. A footer reads: *Research aid. Not investment advice.*

### J5 — Inspect a citation

Clicking a citation opens the source page with the quoted text highlighted, and shows the section path (for example *Strategic report › Principal risks › Supply chain*) and note number where relevant. If a quote could not be verified, it is never shown; the paragraph that relied on it has already been dropped.

---

## 3. Success metrics

Full definitions and fixture formats are in [EVAL.md](EVAL.md). Targets are deliberately conservative.

| Metric | Definition | v1 target on goldens | v1 expectation on held-out report |
|---|---|---|---|
| **Extraction exact-match** | Labelled cells where value, period, page and unit scale all match | **100 %**, or documented rounding. This is a gate, not an aspiration. | Measured and reported, not targeted. Expect 60–85 % coverage. |
| **Silent-wrong rate** | Published (non-null) values that are wrong **and** carry no warning | **0** | **0 is the design goal.** Any occurrence is a P1 bug with a regression test. |
| **Ratio exact-match** | Ratios from the golden pack against hand-computed expected ratios, to 1e-9 | 100 % | n/a (follows extraction) |
| **Citation precision** | Share of displayed citations whose quote exists on the cited page | **100 % by construction.** We also report pre-validation precision to measure model quality. | 100 % by construction |
| **No naked numbers** | Displayed commentary numbers not traceable to `StatementPack`, `RatioPack` or a cited quote | **0 by construction.** Pre-validation rate reported. | 0 by construction |
| **Retrieval hit@8** | Labelled queries whose top 8 chunks include an expected page | ≥ 0.8 | Reported |
| **Human-rated faithfulness** | **Atomic claims** rated "supported" against their cited quotes only, blind to prompt version | ≥ 90 %; 0 contradicted | Reported |
| **Must-cover recall** | Share of the report's principal risks and key audit matters that the commentary covers (objective string match, EVAL E8) | ≥ 0.8 | Reported |
| **Model-originated publications** | Published values whose mapping came from an LLM suggestion or vision alone | **0** (gate) | **0** (gate) |
| **Synthetic layout suite** | Generated statements, one hazard each, truth known by construction (EVAL E7) | 100 % (gate) | n/a |

We do not claim "X % accuracy on annual reports". With 2–3 labelled documents, results are **case studies**, and `docs/RESULTS.md` (written at M8.3) will say so.

---

## 4. Milestones M0–M8

Binary gates and checklists are in [MILESTONES.md](MILESTONES.md). The numbering matches `prompts/03_MILESTONE_PROMPTS.md`.

**Re-sized at review:** the first draft had several milestones that could not be finished in one focused session. Every row below is **one session** (roughly 2–4 hours including your review). The M-level prompt is reused, with "Sub-milestone Mx.y only" added.

| Session | Objective | Key deliverables | You verify by hand |
|---|---|---|---|
| **M0** | Repo contract | Package layout, pyproject, ruff, mypy, pytest (network disabled), CI, `.env.example`, contracts generated from the schema plus a drift check | Layout matches ARCHITECTURE; nothing extra installed |
| **M1** | PDF inspection toolkit | `finintel inspect`: page map, outline, labels, keyword hits, raw text-layer and pdfplumber dumps, raw Azure DI response if a key exists, content-addressed cache | Statement pages findable by eye; page-index convention |
| **M2.1** | Locate statements and profile the document | Page scorer, title scope, hard exclusions, continuation and spreads, document type, classified-balance-sheet test; **synthetic generator** and first specs | Correct income statement and balance sheet pages; company pages rejected |
| **M2.2** | Table model (text-layer family) | `StatementTable` from pdfplumber and PyMuPDF `find_tables`, rows aligned to text-layer lines, styles, sections, notes column, number grammar, multi-page merge | Every golden `raw_text` sits in the right row |
| **M2.3** | Header semantics | Unit and currency (blocking), period columns, restatement, statutory column, entity columns; more synthetic specs | Units and periods on the goldens |
| **M2.4** | Deterministic mapping and pack (local) | Alias map, structural rules, exclusions, arithmetic checks, confidence and τ, `total_debt` presence rule, pack emission, **review-only** LLM pointer, negative tests | Every golden cell, local engines only |
| **M2.5** | Cross-family reconciliation | Azure DI normalised into `StatementTable`; anchoring; text layer re-derives row, column and period; family voting; `ExtractionReport`; review items; τ calibration | One disputed cell's report |
| **M2.6** *(optional)* | Vision family | Corroborate or tripwire only. **Run only if** M2.5 leaves a golden cell unresolved **or** you want a third family. | Tripwire behaviour on a perturbed cell |
| **M3** | Deterministic ratios | `RatioPack` schema; pure functions; `reason` exactly as `CLAUDE.md` says plus `applicability`; flags beside values; changes; property tests | Calculator figures |
| **M4.1** | Section tree and chunker (no database) | Section taxonomy, header and footer removal, reading order, table-region detection, chunking, char→page map, note state machine, footnotes | No table text in prose chunks; note numbers across page breaks |
| **M4.2** | Index and retrieval | Docker Postgres, migrations, FTS, embeddings (Voyage, local, fake), HNSW, RRF, rerank, priors, floor, topic query sets (including bank and NHS variants) | Top 8 for "principal risks" |
| **M5.1** | Commentary contracts and validators (no LLM) | Citation and commentary schemas, placeholder renderer, V1–V8 as pure functions, tests T1–T18 against scripted outputs | Renderer output for each unit scale |
| **M5.2** | Commentary generation | Prompts, `GROUND_TRUTH_NUMBERS` builder, topic and summary calls, retry and drop, extractive mode, persistence, one live run | Claim-level rating; coverage recall |
| **M6.1** | Worker and persistence | Data model (ARCHITECTURE §2.1), jobs with `SKIP LOCKED`, stage runner, retries, timeouts, fallback on failure | One end-to-end run from the CLI |
| **M6.2** | HTTP API | Report, commentary, page, review, overrides, unit, statement location and document type endpoints | One override end to end |
| **M7.1** | Report screen (read-only) | [UI.md](UI.md) layout: header, banners, figures table with row states, ratio cards; Playwright | Every row state renders |
| **M7.2** | Evidence panel and commentary | pdf.js viewer with highlight, provenance panel, commentary with citations, footer | Click every citation |
| **M7.3** | Upload, progress and review | Empty state and upload, stage progress, review actions in the evidence panel, stale banner | An unanchored value is refused |
| **M8.1** | Bank support | Bank alias map, document-type path end to end on `company_b`, applicability matrix in the UI | Label `company_b`; not-applicable cards |
| **M8.2** *(if OQ-4 = B)* | Bank ratios and reported metrics | Cost-to-income, loan-to-deposit; `ReportedMetric` from verified quotes | Against the bank's own figures |
| **M8.3** | Honesty layer | Held-out run (label `company_c` now), `docs/RESULTS.md`, limitations page, README, INTERVIEW refresh | Would you say every sentence of RESULTS in an interview? |

**Total:** 19 sessions, plus 2 optional (21 rows). That is about **5–7 weeks** part-time, which is longer than the draft's estimate, because the draft's session sizes were not honest. M2 is still the long pole.

**Ordering rules (from `CLAUDE.md`, enforced in CI):**
- no `web/` directory before the `m3-done` tag
- no M4.x while M3 is red
- no session starts without its "read first" docs.

---

## 5. Team protocol

### Roles

| Tech lead (you) | Claude Code |
|---|---|
| Chooses and downloads the fixture PDFs; fills in `SOURCES.md` | Never downloads or edits fixtures |
| Hand-labels `fixtures/expected/*.json`, ratios, retrieval, coverage and QA files; **reviews every number in a synthetic spec** | Never creates or edits an expected file. If one is missing, it writes the format and **stops**. May draft synthetic spec layouts for review. |
| Owns `CLAUDE.md`: adds any newly locked ratio (for example OQ-4 B) | Never edits `CLAUDE.md` |
| Answers [OPEN_QUESTIONS](OPEN_QUESTIONS.md) before the milestone that needs them | Raises accounting uncertainty as two options, per `CLAUDE.md`, and never picks the prettier one |
| Pastes **one** milestone prompt per session | Implements only that milestone and adds tests in the same change |
| Checks numbers against the PDF at every gate | Stops and writes a debug note instead of widening scope |
| Commits and tags `mX.Y-done` | Leaves the working tree green and summarises what changed |

### Session ritual

1. Start a fresh Claude Code session in the repo root.
2. Paste the milestone prompt, then: *"Follow CLAUDE.md and docs/MILESTONES.md §Mx. Do not skip ahead."*
3. Claude reads the milestone's "read first" docs before touching code.
4. At the end: tests run, gate checklist ticked in `docs/MILESTONES.md`, open issues listed.
5. You verify by hand, commit on an `mX.Y` branch, merge and tag.

### Stop conditions (take over immediately)

- A ratio is calculated from prose.
- A missing line item is "filled in".
- A ratio definition is changed to make a test pass.
- Parsing is declared "good enough" without matching `expected.json`.
- UI work starts before M3 is green.
- An expected file is edited to make a test pass.
- A value is published from an LLM mapping suggestion or from the vision engine alone.
- A locked ratio's computed value is hidden or replaced for display.
- Work appears that is on the hidden-scope list (§1.1): hosting, extra parser adapters, charts, chat, comps, prices.

---

## 6. Interview narrative (3 minutes)

**0:00–0:30 · The problem.** "Analysts spend hours pulling a few numbers and paragraphs out of 200-page annual reports. Chatbots are fast but invent numbers, and in finance a confident wrong number is worse than no number."

**0:30–1:15 · The design.**
- "I split numbers from narrative. Numbers come from the primary statements, parsed by two independent engines, and every value is anchored to the PDF's own text layer, so a parser can't 'correct' a figure.
- An LLM can suggest which row is operating profit, but it never sees the numbers when it does that, and its suggestion never publishes. Only code with an exact rule, or a person, can publish a figure.
- Ratios are pure Python with locked definitions."

**1:15–2:15 · The demo (golden report).**
- Upload the report. The page chips open the exact cell on the page.
- Show a ratio card with its formula and inputs.
- Click a commentary citation to open the highlighted quote.
- Point out that the model never writes a number: figures are injected from the packs, or copied from a quote that code has verified.

**2:15–2:45 · Honesty.** "Here's the bank. Banks don't split current and non-current, so current ratio is *not applicable*, not zero or a guess. And here's a real failure I hit: [from `RESULTS.md`, for example the parent-company balance sheet picked up instead of the group one], and the check that now catches it."

**2:45–3:00 · Evidence.** "On the labelled reports every cell matches and there are no silent wrong values. On a held-out report coverage was X %, and every miss was a flagged null. The next step is ESEF iXBRL as an independent check."

The four questions in `prompts/04_QUALITY_BAR.md` must be answerable without notes. The full walkthrough and likely questions are in [INTERVIEW.md](INTERVIEW.md); the underlying answers live in [ARCHITECTURE](ARCHITECTURE.md), [EXTRACTION §5](EXTRACTION.md) and [RAG §4](RAG.md).

---

## 7. Blocked on fixtures

Nothing from M2 onwards can be verified until the following exist. The labelling is specified so that it works **whichever way** [OQ-1](OPEN_QUESTIONS.md) (ROCE definition) and [OQ-2](OPEN_QUESTIONS.md) (total debt derivation) are decided. We label a superset.

### 7.1 Before M1 exit

- [ ] `fixtures/pdfs/company_a.pdf`: a FTSE 100 **non-financial** company's full Annual Report and Accounts. It must be digitally born (text selectable), show a line titled **"Operating profit"** on the face of the consolidated income statement, and have **positive total equity**.
- [ ] `fixtures/pdfs/company_b.pdf`: a UK high-street bank's Annual Report and Accounts (needed by M8.1; download now so M1 can inspect it).
- [ ] Optional `fixtures/holdout/company_c.pdf` (**not** `fixtures/pdfs/`; moved at review so no test or inspector touches it): a **held-out** second non-financial company (recommended by OQ-5), or an NHS trust. **Do not open, inspect or label it until M8.3.**
- [ ] A row in `fixtures/pdfs/SOURCES.md` for each PDF.

### 7.2 Before the M1 gate — `fixtures/expected/company_a.json`

Label from the **consolidated (group)** statements only, never the parent-company statements, for **both** the current and the comparative period.

| Canonical id | Where | Notes |
|---|---|---|
| `revenue` | Income statement | Statutory "Revenue" or "Turnover". Not "sales including concessions", not an adjusted or APM figure. |
| `operating_profit` | Income statement | Statutory line only. Not "adjusted", "underlying" or "before adjusting items". |
| `profit_before_tax` | Income statement | |
| `net_income` | Income statement | "Profit for the year" (total, before the split between owners and non-controlling interests) |
| `current_assets` | Balance sheet | Total current assets, which may be an unlabelled subtotal line |
| `current_liabilities` | Balance sheet | Total current liabilities, **stored positive** even if printed in brackets |
| `total_assets` | Balance sheet | **ROCE input.** If not printed, leave it null and label `non_current_assets`; code derives total assets as non-current + current assets (SCHEMA §5) |
| `non_current_assets` | Balance sheet | Proposed v1.1 id. Total non-current assets (may be an unlabelled subtotal) |
| `total_equity` | Balance sheet | Total equity **including** non-controlling interests |
| `equity_attributable_to_owners` | Balance sheet | Proposed v1.1 id. Label it so OQ-11 can go either way. |
| `cash` | Balance sheet | Cash and cash equivalents as shown on the face |
| `borrowings_current` | Balance sheet | Proposed v1.1 id. Interest-bearing borrowings within current liabilities. |
| `borrowings_non_current` | Balance sheet | Proposed v1.1 id |
| `lease_liabilities_current` | Balance sheet | Proposed v1.1 id. Null if not separately presented on the face. |
| `lease_liabilities_non_current` | Balance sheet | Proposed v1.1 id |
| `total_debt` | Derived | Hand-sum of the four lines above. `raw_text: null`, `engine: "hand"`. List the components in the notes file. |

**Conventions** (full rules in [SCHEMA §4](SCHEMA.md#4-conventions-every-labeller-and-every-engine-must-follow)):

- **`page`** is the **1-based PDF page index**: the number your PDF viewer shows as "page X of Y", **not** the folio printed on the page.
- **`value`** is the number as printed, in the statement's unit (so £13,907.5m becomes `13907.5`), sign-normalised: liabilities positive, losses negative.
- **`raw_text`** is exactly as printed, including brackets and commas.
- **`unit_scale`** and **`currency`** come from the statement column header.
- **Period ids** follow the pattern `FY2025`, using the calendar year of the period end. The `label` is as printed ("52 weeks ended 29 March 2025"). Set `is_restated: true` if the column says "restated".
- **`confidence: 1.0`** and **`engine: "hand"`** for every labelled cell.
- Record every judgement call in **`fixtures/expected/company_a.labelling_notes.md`**: what counts as borrowings, whether overdrafts are included, where leases sit, and anything odd.
- Also record in the notes file (the v1.0 schema has no field for these):
  - the **note reference** printed beside each labelled line (for example "22")
  - whether the balance sheet is **classified** (has current and non-current sections)
  - whether any statement shows **Group and Company columns side by side**.

### 7.3 Before M3 — `fixtures/expected/company_a.ratios.json`

Calculator-computed ratios for **both** periods using the locked formulas in `CLAUDE.md` (ROCE = operating profit ÷ (total assets − current liabilities)). Format: [EVAL §3.2](EVAL.md).

### 7.4 Before M4.2 — `fixtures/expected/company_a.retrieval.json`

Five queries, each with the PDF page indices where the answer lives:

1. Principal risks
2. Going concern or viability
3. Main revenue drivers or segment performance
4. Audit committee significant issues or key audit matters
5. Borrowing facilities or liquidity headroom

### 7.4a Before M5.2 — `fixtures/expected/company_a.coverage.json`

The report's principal risk names, key audit matter titles and going-concern conclusion, with pages ([EVAL §3.6](EVAL.md)). About 30 minutes.

### 7.5 Before M5.2 — `fixtures/expected/company_a.qa.json`

Twenty questions in the [EVAL §3.4](EVAL.md) format.

### 7.6 Before M8.1 — `fixtures/expected/company_b.json`

Bank items per the decision on [OQ-4](OPEN_QUESTIONS.md).

**Estimated labelling time:** about 2 hours for 7.2 and 7.3, 30 minutes each for 7.4 and 7.4a, 1 hour for 7.5, and 2 hours for 7.6.
