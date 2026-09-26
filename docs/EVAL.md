# EVAL — how we know it works

This is a real harness, not a judgement of whether the output reads well. Every number in `docs/RESULTS.md` (M8.3) must come from a run of this harness, with the run id.

---

## 1. Principles

1. **Goldens are truth.** Expected files are written by the tech lead from the PDF. Code never creates or edits them. A mismatch is a code bug until the tech lead says the label was wrong, and a label fix is recorded in `fixtures/expected/CHANGELOG.md`.
2. **Separate what we tune on from what we measure on.**
   - `company_a` (and `company_b` from M8.1) are **development goldens**.
   - `company_c`, if provided, is **held out**: not labelled and not looked at until M8.3, then labelled and scored once. Tuning on it afterwards makes it a development golden, and `RESULTS.md` must say so.
   - The held-out PDF lives in **`fixtures/holdout/`**, which is git-ignored and **excluded from every test and every inspector run until M8.3** (fixed at review). In the draft it sat in `fixtures/pdfs/`, so M1's "run on every fixture" gate would already have processed it.
3. **With two or three documents, results are case studies, not accuracy rates.** Report counts ("41/41 cells"), not percentages dressed up as population estimates.
4. **Silent-wrong is the metric that matters most.** A null with a warning is an acceptable failure. A confident wrong number is not.
5. **Offline by default.** CI runs only offline suites, using cached parser artefacts and the `fake` LLM provider. Live runs are manual, traced and costed.

---

## 2. Suites

| Suite | What it checks | Where it runs |
|---|---|---|
| **E1 Golden cells** | Extracted `StatementPack` against `fixtures/expected/{company}.json` | CI **on committed excerpts in `tests/golden/`** (ADR-009, if OQ-10 = yes); full PDF locally with `make eval`. The draft's "CI on cached artefacts" was impossible, because `artifacts/` and the PDFs are git-ignored. |
| **E2 Ratios** | `compute_ratios(expected pack)` and `compute_ratios(extracted pack)` against `{company}.ratios.json`; property tests | CI |
| **E3 Retrieval** | Top-8 evidence against `{company}.retrieval.json` | CI (local embeddings, cached) and live (Voyage) |
| **E4 Commentary** | Offline validator tests (RAG §6, T1–T18); live pre- and post-validation rates; **claim-level** human rating (§4) | CI (offline) and live |
| **E5 QA-20** | 20-question grounded-answer set per golden (§3.4) | Live only |
| **E6 Negative and property** | Removed revenue row gives null; perturbed engine gives disagreement; ×1000 scale leaves ratios unchanged; a sign flip fails an arithmetic check; company-only page never chosen; **no published value has method `llm_pointer`**; **no value published on vision alone**; a lease row that is present but null gives `total_debt` null | CI |
| **E7 Synthetic layout suite** (added at review) | ≥ 12 generated statement PDFs (ADR-010), each isolating one hazard: £000 / £m / missing unit; brackets / minus; notes column; columnar income statement; unlabelled subtotal; company page before group; Group \| Company columns; restated header; two-page balance sheet; liquidity-ordered balance sheet; net-assets format with negative liabilities; spread page. Truth is the generating spec. | CI |
| **E8 Must-cover facts** (added at review) | Objective content check: does the commentary mention the facts a credit analyst must see? Scored by exact or alias string match against `{company}.coverage.json` (§3.6). **Not a judgement of whether the prose reads well.** | Live, replayable offline |

---

## 3. Fixture formats

### 3.1 `{company}.json`: expected StatementPack

A valid `StatementPack`, v1.0.0 or (once approved) v1.1.0.
- Every cell has `engine: "hand"` and `confidence: 1.0`.
- Every cell has `page` and `raw_text`, except derived `total_debt`.
- Only labelled items are compared. Unlabelled canonical items are not scored, **unless** labelled explicitly as `value: null`, which means "the correct answer is null" and is scored.
- Judgement calls go in `{company}.labelling_notes.md`.

**Comparison rules:**

| Field | Rule |
|---|---|
| `value` | Exact match (tolerance 0 in printed units), unless `labelling_notes.md` documents rounding for that cell |
| `period_id` | Exact |
| `page` | Exact (PDF page index) |
| `unit_scale`, `currency` | Exact at pack level. **A mismatch fails every cell.** |
| `raw_text` | Normalised equality (commas, spaces and bracket styles unified) |

### 3.2 `{company}.ratios.json`: expected ratios

A list of period objects in the same shape as `EXAMPLE_company_a.ratios.json`. A single object is accepted for backwards compatibility.

```json
[
  { "period_id": "FY2025", "formulas_locked": true,
    "ratios": {
      "operating_margin": { "value": 0.170109356, "formula": "operating_profit / revenue", "inputs": { "operating_profit": 2100.0, "revenue": 12345.0 } },
      "current_ratio":    { "value": 1.538461538, "formula": "current_assets / current_liabilities", "inputs": { "current_assets": 8000.0, "current_liabilities": 5200.0 } }
    },
    "alternatives": {
      "roce_option_b": { "value": 0.141891892, "formula": "operating_profit / (total_assets - current_liabilities)", "inputs": { "operating_profit": 2100.0, "total_assets": 20000.0, "current_liabilities": 5200.0 } }
    }
  },
  { "period_id": "FY2024", "formulas_locked": true, "ratios": { } }
]
```

- The figures above are the fictional `EXAMPLE` numbers, shown for shape only.
- Values are typed from a calculator to **at least 9 decimal places**. Tolerance is 1e-9 absolute.
- A ratio that should be null is written `"value": null` with `"reason"` (`missing_input` or `division_by_zero`), and the null input shown as `null`. Applicability is written separately: `"applicability": "not_applicable"` with an `explanation` (ADR-008).
- `alternatives` is used only if OQ-1 keeps option B under consideration. It is scored separately and never replaces a locked ratio.

### 3.3 `{company}.retrieval.json`

```json
{ "queries": [
  { "id": "r1", "q": "What are the principal risks?", "topic": "strategic_risks",
    "must_include_page_any_of": [58, 59, 60], "section": "principal_risks" }
] }
```

Five queries minimum (PLAN §7.4). Pages are PDF page indices.

### 3.4 `{company}.qa.json`: the 20-question set

These run through an **eval-only** function `evals.ask(question, document)`. It uses the same retrieval, prompt contract and validators as commentary, with the question as the query. It is **not** exposed in the API or UI; v1 has no chat.

```json
{ "document": "company_a", "questions": [
  { "id": "q01", "type": "numeric_lookup", "question": "What was statutory operating profit in FY2025?",
    "expected": { "placeholder": "item:operating_profit:FY2025" } },
  { "id": "q07", "type": "narrative", "question": "What does the board conclude on going concern?",
    "expected": { "pages_any_of": [101, 102], "must_mention_any_of": ["going concern"] } },
  { "id": "q16", "type": "absent", "question": "What is the group's exposure to cryptocurrency?",
    "expected": { "status": "insufficient_evidence" } },
  { "id": "q19", "type": "trap", "question": "Should I buy the shares?",
    "expected": { "no_advice": true } }
] }
```

**Required mix:**

| Type | Count | Examples |
|---|---|---|
| `numeric_lookup` | 6 | Answer must use the right placeholder and contain no naked numbers |
| `narrative` | 8 | At least one verified citation on an expected page, and the required terms present |
| `absent` | 3 | Must return `insufficient_evidence` |
| `trap` | 3 | One adjusted/APM figure ("What was adjusted operating profit?", which must not produce a statutory placeholder mislabelled as adjusted); one company-only figure; one advice request |

### 3.5 Other fixture files

- `{company}.labelling_notes.md`: every judgement call, per cell where needed.
- `fixtures/expected/CHANGELOG.md`: any label correction, with date, cell, old value, new value and reason.

### 3.6 `{company}.coverage.json`: must-cover facts (added at review)

Written by the tech lead from the report, about 30 minutes per report.

```json
{ "document": "company_a",
  "principal_risks": [ { "name": "Supply chain disruption", "aliases": ["supply chain"], "page": 58 } ],
  "key_audit_matters": [ { "name": "Impairment of store assets", "aliases": ["store impairment"], "page": 131 } ],
  "going_concern": { "conclusion": "material_uncertainty_absent", "page": 101 },
  "viability_period_years_text": "three years",
  "must_not_claim": ["material uncertainty"]
}
```

**Scoring:**

| Metric | Definition |
|---|---|
| **Risk recall** | Share of `principal_risks` whose name or an alias appears in a **displayed** paragraph that cites a chunk on or near (±2 pages) the listed page |
| **KAM recall** | Same, for `key_audit_matters` |
| **Going-concern correctness** | The governance topic states the conclusion consistently: `must_not_claim` phrases absent unless quoted |

### 3.7 Synthetic layout specs (`evals/synthetic/specs/*.yaml`)

Each spec lists the statement type, unit token, column headers, rows (label, style, section, values per period) and the hazard it exercises. The generator renders the PDF and writes the expected pack. **The spec is the only source of truth, and the spec is written by a human.** Claude Code may draft a spec's layout, but every numeric value in a spec is reviewed by the tech lead before commit.

---

## 4. Target scores for v1

These are conservative and honest. "By construction" means the validator makes any other result impossible, so anything else is a bug.

| Metric | `company_a` (dev golden) | Held-out corporate (`company_c`) | Bank (`company_b`, M8.1) |
|---|---|---|---|
| E1 cell exact-match | **100 %** (gate) | Measured; expect 60–85 % coverage | 100 % of labelled bank cells, or null with a warning |
| E1 silent-wrong cells | **0** (gate) | **0** goal. Each case is a P1 with a regression test. | **0** (gate) |
| E1 unit or currency errors | **0** (gate) | 0 (blocked, not guessed) | 0 |
| E2 ratio exact-match | **100 %** (gate) | n/a | 4/4 corporate ratios `value: null`, `reason: missing_input`, `applicability: not_applicable` (gate) |
| E6 published values with method `llm_pointer`, or on vision alone | **0** (gate) | **0** (gate) | **0** (gate) |
| E7 synthetic layout suite | **100 %** of spec cells, or the spec's expected null (gate) | n/a | n/a |
| E8 risk recall / KAM recall | ≥ 0.8 / ≥ 0.8 | Reported | Reported |
| E8 going-concern correctness | **Correct** (gate) | Reported | Reported |
| T17 ground-truth sensitivity | **Pass** (gate) | n/a | n/a |
| E3 retrieval hit@8 | ≥ 0.8 | Reported | Reported |
| E4 citations displayed but unverifiable | **0** (by construction) | 0 | 0 |
| E4 naked numbers displayed | **0** (by construction) | 0 | 0 |
| E4 pre-validation fabricated-quote rate | ≤ 5 % of citations | Reported | Reported |
| E4 pre-validation paragraphs with a naked number | ≤ 10 % | Reported | Reported |
| E4 human faithfulness | ≥ 90 % "supported"; **0 "contradicted"** | Reported | Reported |
| E4 mandatory topics with status `ok` | 3/3 | Reported | Reported |
| E5 QA-20 | ≥ 17/20 | n/a | n/a |

**Human rating protocol (E4), tightened at review.** The draft rated whole paragraphs, which drifts towards "does it sound right".
1. `make eval-live` splits each displayed paragraph into **atomic claims** (one proposition each) using a deterministic sentence and clause splitter, and writes a rating sheet.
2. For each claim, the rater sees **only** the claim and its cited quotes. The model id and prompt version are hidden, so prompt versions can be compared blind.
3. Each claim is rated **Supported**, **Partially supported**, **Unsupported** or **Contradicted**.
4. Ratings are stored in `artifacts/eval/{run_id}/ratings.json`.
5. "Partially" counts as a miss for the 90 % target.
6. The rating is **one** of five content checks (E4 validators, E8 coverage, T17 sensitivity, E5 QA-20, human rating). No single check, and certainly not fluency, can pass the commentary on its own.

---

## 5. Error taxonomy

Every E1 and E4 failure is classified, automatically where possible. The classifier compares the extracted value with the expected value, using the table rows in `ExtractionReport`.

| Code | Definition | Automatic detection rule | Example |
|---|---|---|---|
| `unit` | Scale wrong | extracted = expected × 10^±3 or 10^±6, or pack `unit_scale` ≠ expected | 13,907,500 recorded at £m scale |
| `sign` | Sign wrong | extracted = −expected | Current liabilities stored negative |
| `wrong_row` | Value from another row | extracted equals another row's value in the same statement table | Gross profit mapped as operating profit |
| `wrong_period` | Value from another period column | extracted equals the expected value for another period | FY2024 value under FY2025 |
| `dropped_comparative` | Comparative missing | expected non-null for a comparative period, extracted null, current period correct | Prior-year column lost across a page break |
| `wrong_statement_scope` | Company-only statement used | extracted page is tagged `scope=company` | Parent-company balance sheet |
| `apm_confusion` | Adjusted figure chosen | extracted equals a candidate that was excluded by an APM pattern, or a highlights-page value | Adjusted operating profit |
| `note_column_value` | Note reference read as a value | extracted equals the row's note reference | "12" as current liabilities |
| `multi_page_split` | Row lost or duplicated at a page break | expected row's page is a continuation page and the value is missing or duplicated | Total equity on the second page not found |
| `restatement_missed` | Restated column not flagged | expected `is_restated: true`, extracted false | |
| `unanchored_value` | Published value not in the text layer | anchoring re-check fails. **Should be impossible; any occurrence is P0.** | |
| `bad_citation` | Displayed quote not on the cited page | quote re-verification against the page text fails. **By construction impossible; P0.** | |
| `arithmetic_in_prose` | Commentary number not traceable | V5 re-check on displayed text | "margin up 1.3 points" |
| `advice_language` | Investment advice displayed | V6 re-check | "undervalued" |
| `retrieval_miss` | No expected page in the top 8 | E3 | |
| `other` | Needs a human | none of the above | Recorded with a note |

---

## 6. Harness mechanics

| Command | Does | Network |
|---|---|---|
| `make test` | Unit, property, E2, E6, E7, E4-offline, and E1 on `tests/golden/` excerpts (if OQ-10 = yes) | None |
| `make eval` | E1 and E3 against **cached** stage artefacts, plus everything in `make test`; writes `artifacts/eval/{run_id}/report.{md,json}` | None |
| `make eval-live COMPANY=company_a` | Full pipeline with live engines and LLMs, then E1–E5; records **cost and latency per stage** and Langfuse trace ids | Yes |

- **Baselines:** `evals/baselines/{company}.json` holds the last accepted metrics. `make eval` fails if any gate metric gets worse. Updating a baseline needs a line in `evals/baselines/CHANGELOG.md` explaining why.
- **Report content:** the metrics table (§4); every failure with its taxonomy code, page and a rendered crop; confidence distributions; engine agreement rates; validator rejection counts by code; cost and latency.
- **Record/replay:** live LLM and embedding responses are cached by request hash, so a live run can be replayed offline and give identical results. This is how E4 and E5 findings become regression tests.

### 6.1 Calibrating τ and the confidence weights (at M2.5)

1. On the dev goldens, list every candidate's confidence alongside whether it was correct.
2. Choose the **lowest τ that publishes zero wrong values** on the goldens. If that τ is below 0.80, **keep 0.80**: we do not loosen on the evidence of two documents.
3. Record the choice and the evidence in [EXTRACTION §5.3](EXTRACTION.md).
4. Re-check on the held-out report at M8.3 and report honestly if it breaks.
