# EXTRACTION — from PDF to StatementPack

This is the implementation design for M1–M2.6 (M2 is split into sessions M2.1–M2.6; see MILESTONES). It is written to be implemented **without improvisation**: where a threshold or rule is needed, it is stated here. Where a number here turns out to be wrong on the goldens, change it in this document first (with the evidence), then in code.

Pipeline:

```
PDF → text layer → locate statements → engines → StatementTable (per engine)
    → units + periods → mapping candidates → anchoring → voting + arithmetic checks
    → StatementPack + ExtractionReport → review queue
```

---

## 0. Inputs and the digital-born check

- **Text layer (PyMuPDF):** words with bounding boxes, font name, size and flags (bold), block and line ids, plus the PDF outline and page labels. This is the **anchor of truth for characters**.
- **Digital-born score:**
  - share of pages with ≥ 200 extractable characters
  - share of those characters that are not replacement glyphs.
- **Threshold (initial):** ≥ 0.9 of pages pass. Below that:
  - `not_digitally_born`
  - OCR-derived values (Azure DI on a scan) are **capped at confidence 0.60**, below τ
  - they appear only as review suggestions.
  This is the "measured fallback, not the happy path" rule.
- **Encrypted or password-protected PDFs** are rejected at upload.

---

## 1. Locate candidate statement pages

Statement types in v1:
- `income_statement` (including a combined "statement of comprehensive income" when no separate income statement exists)
- `balance_sheet` (statement of financial position).

The cash flow statement and statement of changes in equity are located (for continuity and future use) but not extracted.

### 1.1 Signals per page

| Signal | Weight | Detail |
|---|---|---|
| **Title match** | 0.40 | Title-like text (top 25 % of the page, font size ≥ 1.2× page median, or bold) matching a statement title pattern. **Corporate:** "consolidated/group income statement", "consolidated statement of profit or loss", "consolidated statement of comprehensive income", "consolidated/group balance sheet", "consolidated statement of financial position". **NHS:** "statement of comprehensive income", "statement of financial position". **Bank:** same as corporate. |
| **Outline or contents hit** | 0.20 | The PDF outline, or the printed contents page (title → printed page → PDF page via page labels), points at this page for a statement title |
| **Numeric density** | 0.20 | Share of tokens parseable as numbers ≥ 0.30, **and** at least 8 rows with ≥ 2 numeric cells |
| **Column header pattern** | 0.10 | Two or more year or date tokens in one line near the top of the table (for example `2025 2024`, `29 March 2025`) and a unit token (`£m`) |
| **Row vocabulary** | 0.10 | Hits on statement vocabulary: revenue, cost of sales, operating profit, finance costs, taxation (income statement); non-current assets, current assets, current liabilities, net assets, total equity (balance sheet) |

### 1.2 Hard exclusions and scope

**Scope classification** from the title line:
- "Company", "Parent company", "Company balance sheet", "Company statement of financial position" → `scope=company` → **excluded** from v1 values.
- "Consolidated" or "Group" → `scope=group`.
- If the report has only one set of statements and no qualifier (typical of NHS trusts) → `scope=single_entity`.

**Never statement candidates, whatever their score:**
- highlights or KPI pages
- financial review or CFO review pages
- five- or ten-year summaries
- alternative performance measure (APM) reconciliations
- segment notes
- the independent auditor's report.

These are detected by running header, title and section tree ([RAG §1](RAG.md)). This is the main defence against **APM contamination**: the same numbers, or adjusted versions of them, appear on these pages.

### 1.3 Selection

- For each statement type, choose the highest-scoring `scope=group` page with a score ≥ 0.55.
- If two group pages are within 0.05 of each other, keep both and raise `entity_scope_ambiguous`; both go to review.
- If none reaches the threshold, the statement is `not_found`, its items are null, and `missing_item` is raised.

Output: `StatementLocation {statement_type, scope, pages[], score, signals[]}`, persisted in `ExtractionReport`.

If a statement is `not_found`, the analyst can **point to the page** (`POST /reports/{id}/statement-location`, §6). The locator then re-runs constrained to that page. This is a human decision about *where* to look, never a number.

### 1.4 Document type and balance-sheet classification (decided before mapping)

**Ratio applicability is decided by what the balance sheet actually presents, not by a label.** This covers banks, insurers and investment entities with the same rule.

| Test | Rule | Consequence |
|---|---|---|
| **Classified balance sheet?** | The located balance sheet has section headers matching "current assets" **and** "current liabilities" (or the Companies Act "creditors: amounts falling due within one year") | If **no** (a liquidity-ordered presentation, as IAS 1.60 permits): `current_assets` and `current_liabilities` are null by design, with `unclassified_balance_sheet`; current ratio `applicability = not_applicable` |
| **Bank signals** | Balance sheet has "loans and advances to customers" **and** ("customer deposits" or "deposits from customers"); income statement has "net interest income" | `document_type = bank`, bank alias map, `bank_layout` |
| **NHS signals** | Two or more of: "public dividend capital", "taxpayers' equity", "NHS" or "Department of Health and Social Care" in statement titles or notes headers, "operating income from patient care activities" | `document_type = nhs_trust`, NHS alias map, `public_sector_layout` |
| **Corporate** | Classified balance sheet, a revenue alias on the income statement, no bank or NHS signals | `document_type = corporate` |
| **Otherwise** | Signals conflict (for example a retailer with a banking subsidiary) or none apply | `document_type = other` plus `document_type_ambiguous`. **All four corporate ratios are withheld** until a reviewer sets the type (§6). |

The per-ratio applicability matrix, which lives in code as data:

| Ratio | Corporate | Bank | NHS trust | Other / unclassified balance sheet |
|---|---|---|---|---|
| Operating margin | applicable | not applicable (no revenue line) | per OQ-5 | withheld |
| Current ratio | applicable | not applicable (unclassified) | applicable (the NHS SoFP is classified) | not applicable |
| Debt-to-equity | applicable | not applicable (deposits are not corporate debt) | per OQ-5 | withheld |
| ROCE | applicable | not applicable | per OQ-5 | withheld |

---

## 2. Reconstruct multi-page tables

1. **Continuation detection.** Page *p+1* continues statement *S* on page *p* if **all** of the following hold:
   - no new statement title in its top region
   - a numeric table with the **same number of value columns**, and either the same header year tokens or a "continued" marker
   - consecutive page labels, where these exist.
2. **Spreads.** If a page's width-to-height ratio is > 1.3 and it has two folio numbers, treat the left and right halves as separate sub-pages for table reconstruction. `page` stays the PDF page index, and each row's bounding box records which half it came from.
3. **Merge.** Append the rows in order. Carry the current section header (for example "Current liabilities") across the break. **Every row keeps its own page.**
4. **Engine specifics.**
   - Azure DI may return one table with several bounding regions across pages, or separate tables. Both are normalised by the same rule.
   - pdfplumber tables are extracted per page and merged by rule 3.
5. Raise `multi_page_table` (info) whenever a merge happened, so reviewers know to check the page boundary.

---

## 3. Units, currency and periods

- **Unit and currency:** per [SCHEMA §7](SCHEMA.md#7-unit_scale-and-currency-rules). Exactly one unit token per statement; the income statement and balance sheet must agree; otherwise **block**.
- **Periods:** per [SCHEMA §8](SCHEMA.md#8-periods-and-comparative-columns). Column → period is decided from parsed dates, never from position.
- **Note column:** a column is the note column if its header is "Note" or "Notes", **or** at least 80 % of its non-empty cells match `^\d{1,2}(\.\d{1,2})?([,/]\s?\d{1,2}(\.\d{1,2})?)*$` and it lies between the label column and the first value column. The note column is **never** a value column, but note references are stored on the row (they feed citations and review).
- **Columnar income statements** ("before adjusting items / adjusting items / total"): only the column whose header matches `total|statutory` is a value column. Otherwise raise `period_ambiguous` and the values are null.
- **Column-level scope.** Some statements put entities side by side: "Group | Company", or in NHS group accounts "Group | Trust". The column header band is scope-classified in the same way as titles (§1.2). **Only group or consolidated columns are value columns.** If there are entity columns but none is identifiable as the group, raise `entity_scope_ambiguous` and the values are null.

---

## 4. Map rows to canonical items, with confidence

### 4.1 `StatementTable` (per engine, per statement)

```
StatementTable
  statement_type, scope, engine, pages[]
  columns[]: {column_id, header_text, kind: label|note|value, period_id, is_restated, is_total_column}
  rows[]:    {row_id, label_text (multi-line joined), note_ref, section_header,
              indent_level, style: total|subtotal|normal|header, page,
              cells: {column_id: {raw_text, parsed_value, bbox, page}}}
```

**Row style comes from the text layer** (bold font flag, ruling lines within 3 pt above or below, larger font), not from engine guesses. Every engine's rows are **aligned to text-layer lines by y-overlap**, which is what lets different engines be compared row by row.

### 4.2 Parsing printed numbers

Grammar (after Unicode NFKC):
- optional currency symbol
- optional `(`...`)` or leading minus (hyphen, en dash, Unicode minus) for negatives
- digits with `,` or thin-space thousands separators
- optional `.` decimal
- optional trailing footnote marker (`*`, `†`, `‡`, superscript digits)
- a lone dash, "nil" or "–" means zero.

Anything else (for example "n/a" or "see note 12") leaves the cell **unparsed**; it is recorded but never becomes 0.

### 4.3 Deterministic mapping

Apply in order. The first rule that produces a **unique** candidate wins.

1. **Exact alias** within the correct statement and section context ([SCHEMA §6](SCHEMA.md#6-alias-map-approach)). Method `exact_alias`.
2. **Regex alias.** Method `regex_alias`.
3. **Structural rules.** Method `structural`:
   - *Unlabelled subtotal:* a row with an empty label, styled as total or subtotal, directly after the last row of a section, whose value equals the sum of that section's rows within tolerance (§5.2). Maps to `current_assets`, `current_liabilities` and so on for that section.
   - *Net assets = total equity:* in net-assets-format balance sheets, the equity total is the row that equals "Net assets".
4. **Exclusion filter.** Any candidate matching an alias `exclude_any` pattern is removed, whatever rule produced it.

### 4.4 Number-blind LLM pointer (for leftovers only)

Used only when §4.3 leaves a canonical item without a unique candidate, and an LLM key exists.
- **Input:** document type, statement type, and the table rows as `{row_id, label_text, section_header, indent_level, style, page}`, with **every digit masked** (`<num>`). The model cannot see magnitudes and so cannot prefer a "plausible" number.
- **Output:** for each requested canonical id, `{row_id or null, reason}`. The schema forbids numeric fields.
- **Model:** the frontier model; temperature 0; cached by input hash; prompt version recorded.
- **Persisted separately** in `artifacts/{sha}/mapping_suggestions/{engine}.json`. Suggestions are never written into the pack directly.
- Code checks that the row exists, is in the right statement and section, and survives the exclusion filter. Only then is the suggestion a candidate, with method `llm_pointer`.
- **An `llm_pointer` candidate never publishes.** Its confidence is hard-capped at 0.70, below τ. It appears only in the review queue, pre-selected as "Suggested by model: needs your confirmation" ([ADR-007](ARCHITECTURE.md)).
- *Why a hard cap and not corroboration:* neither of the obvious corroborations actually checks a mapping.
  - **Engine agreement** only shows that two engines read the *same cell* the same way.
  - **Arithmetic checks can pass for the wrong row.** "Gross profit" satisfies `row = revenue + Σ rows between them` just as well as "Operating profit" does.
  - So only a human can confirm what a row *means*.

---

## 5. Reconcile engines

### 5.1 Anchoring (every candidate, every engine)

A candidate `(raw_text, page, bbox?)` is **anchored** if its normalised `raw_text` is found in the PyMuPDF text layer of that page:

- **Engines with bounding boxes** (pdfplumber, PyMuPDF `find_tables`, Azure DI; Reducto, LlamaParse and Docling in v1.1): search within the bounding box expanded by 2 pt.
- **Vision:** no bounding boxes.
  1. Find the text-layer line matching the vision row label (normalised similarity ≥ 0.9).
  2. Find the text-layer column band matching the vision column header.
  3. The printed value must appear **exactly once** at the intersection.
- **Normalisation for matching only:** remove thousands separators and spaces; map `(x)`, `-x` and `−x` to one negative form; map dashes and "nil" to 0.

**An unanchored candidate is discarded** and logged as `unanchored_candidate` in `ExtractionReport`. This one rule makes generative parsers and the vision vote safe: they can help find a number, but they can never introduce one.

**After anchoring, the text layer decides row, column and period.**
- Code finds which text-layer line the anchor sits on (that gives the row label) and which column band it sits in (that gives the period, via §3).
- **The engine's own row, column and period claims are discarded.**
- This closes the path where an engine anchors a *real* number to the *wrong* cell (for example a prior-year value reported under the current-year column): the number exists on the page, but code, not the engine, says what it is.

### 5.1a Engine families

| Family | Members in v1 | Independence |
|---|---|---|
| `text_layer` | pdfplumber, PyMuPDF `find_tables()` | Both read the same embedded text and positions, so their errors are **correlated** |
| `image_layout` | Azure DI `prebuilt-layout` | Independent of the text layer: a layout model working on the rendered page |
| `vision` | Frontier multimodal model (optional, M2.6) | Independent, but model-generated. It **corroborates only** (§5.4). |

**Agreement counts only across families.** Two text-layer engines agreeing is treated as one engine.

### 5.2 Arithmetic checks (deterministic, only where the rows are printed)

| Check | Statement |
|---|---|
| `current_assets` = Σ rows under "Current assets" | Balance sheet |
| `current_liabilities` = Σ rows under "Current liabilities" | Balance sheet |
| `total_assets` = `non_current_assets` + `current_assets` | Balance sheet |
| `net_current_assets` = `current_assets` − `current_liabilities` | Balance sheet |
| `total_assets` − `total_liabilities` = `total_equity` (or Net assets = Total equity) | Balance sheet |
| `total_equity` = Σ equity component rows (including NCI) | Balance sheet |
| `operating_profit` = `revenue` + Σ operating income/expense rows between them | Income statement |
| `profit_before_tax` = `operating_profit` + Σ finance and other rows between them | Income statement |
| `net_income` = `profit_before_tax` + tax row | Income statement |

**Tolerance:** `|difference| ≤ 0.5 × n × u`, where *n* is the number of printed figures in the equation and *u* is the unit of the last printed digit (1 for integers, 0.1 for one decimal place). This allows for published rounding, and nothing more.

A failed check **never changes a value**. It lowers confidence and raises `arithmetic_check_failed`, which names the check and the difference.

### 5.3 Confidence and publication

For each canonical item × period, compute the following **deterministically**:

```
base        = { exact_alias: 0.95, regex_alias: 0.90, structural: 0.85 }[method]   # deterministic methods only
agreement   = × 1.00 if anchored candidates from ≥ 2 engine FAMILIES (§5.1a) agree on the same text-layer cell
              × 0.90 otherwise (one family; the two text-layer engines count as one)
vision      = counts as a second family ONLY when it anchors to the same text-layer cell as a deterministic candidate
arithmetic  = + 0.05 if ≥ 1 check involving this cell passes
              − 0.30 if any check involving this cell fails
caps        = min(0.99, …); ≤ 0.85 after a resolved disagreement (§5.4); ≤ 0.60 if not_digitally_born
llm_pointer = fixed 0.70, never publishes (§4.4)
publish if confidence ≥ τ (τ = 0.80); otherwise value = null + low_confidence + review item
```

Consequences, with worked values:
- Exact alias, Azure DI and pdfplumber agree, a check passes → 0.99, published.
- Exact alias, local engines only, no check available → 0.855, published.
- Structural subtotal, local engines only, check passes (the structural rule is itself arithmetic) → 0.815, published.
- **LLM pointer → 0.70 whatever the evidence → review only.**
- **Vision alone → no candidate at all** (vision is never a mapping method).
- τ and the weights are **initial values**. They are calibrated on the goldens at M2.5 (after both engine families run), and any change is recorded here. They must never be tuned to make a failing golden pass.

### 5.4 Voting

1. Collect the anchored candidates produced by **deterministic mapping** (exact alias, regex alias, structural) on each engine's table.
2. **All agree** (same text-layer cell) → accept. `engine: reconciled` if two or more families agree, otherwise the engine's own name.
3. **Only one family produced a candidate** → accept with the single-family multiplier.
4. **Vision's role:** it can only **corroborate** (it anchors to the same cell, so a second family agrees) or act as a **tripwire** (it anchors to a different cell, which raises `parser_disagreement` and caps confidence at 0.79, sending the item to review). **Vision never breaks a tie and never supplies the only candidate.**
5. **Disagreement between deterministic candidates** → tie-break using deterministic evidence only, all of which must hold for exactly one candidate:
   - its text-layer row label matches the alias for the canonical id
   - its column maps to the right period
   - it passes every applicable arithmetic check.
   - If exactly one candidate satisfies all three → accept, cap confidence at 0.85, and raise `parser_disagreement` ("resolved: …").
   - Otherwise → **null** with `parser_disagreement` ("unresolved: azure_di=1,234 p.142; pdfplumber=1,243 p.142"), and every candidate goes to review.
6. **Never** choose by magnitude, "plausibility", closeness to a narrative figure, engine reputation, or a model's opinion.

### 5.4a `total_debt` presence rule (implements SCHEMA §5)

For each debt component (borrowings current and non-current; lease liabilities current and non-current):

| Situation | Treatment |
|---|---|
| Component row found and published | Use its value |
| Component row found but **null** (low confidence, disagreement or pending review) | **`total_debt` = null** with `missing_input`. Never "borrowings only". |
| No row matches the component anywhere in its section, **and** that section's subtotal check passed (proving every row was seen) | Component = 0, recorded in `derived_from` as `{"item": "...", "assumed_zero": true}` |
| No matching row, and the section subtotal check did not pass or could not run | **`total_debt` = null** |
| No lease rows on the face, borrowings resolved, and the lease rule applies | Borrowings only, plus `lease_not_separately_presented`, as `CLAUDE.md` specifies |

### 5.5 Outputs

- **`StatementPack`**, valid against the schema, with `source.parser_engines` = the engines that ran.
- **`ExtractionReport`** (internal): for each item and period, every candidate, its anchoring result, the checks run with their differences, the method, the confidence arithmetic and the decision. **This is the first thing to read when a golden fails.**
- **Review items** for every null that has at least one candidate, and every resolved disagreement.

---

## 6. Human review API (implemented in M6.2, UI in M7.3)

| Endpoint | Purpose |
|---|---|
| `GET /reports/{id}/review` | Review items: item, period, candidates (with engine, page, raw_text, bounding box), warnings, reason |
| `POST /reports/{id}/overrides` | See below |
| `POST /reports/{id}/unit-confirmation` | `{currency, unit_scale, evidence_page}`. Unblocks a `needs_unit_confirmation` report. The pack then carries a permanent `unit_confirmed_manually` warning and a visible badge. |
| `POST /reports/{id}/statement-location` | `{statement_type, page}`. Re-runs location and extraction constrained to that page. Used when a statement is `not_found` or `entity_scope_ambiguous`. |
| `POST /reports/{id}/document-type` | `{document_type, reason}`. Resolves `document_type_ambiguous`; the applicability matrix (§1.4) is re-applied. |
| `GET /reports/{id}/overrides` | Audit trail (append-only) |

`POST /reports/{id}/overrides` accepts one of three actions:
- `accept_candidate`: requires `candidate_id`.
- `set_value`: requires `value`, `raw_text` and `page`. The server searches the text layer of `page` for `raw_text`. **If it is not there, the response is `422 unanchored_override`**, unless `force: true` is sent with a `reason`, in which case the override is recorded with the flag `unanchored`.
- `set_null`: requires a `reason`.

Effects of every accepted override:
1. It is appended to the `overrides` table (who, when, before, after, reason).
2. A new pack version is materialised: extracted values plus overrides, with `engine: human_override` and confidence 1.0. A **forced (unanchored)** override carries `human_override_unanchored`. The UI shows it with an amber "Manual: not found on page" badge, and every ratio that uses it inherits the badge.
3. The `RatioPack` is recomputed.
4. Existing commentary is marked `stale`.

**Overrides never touch `fixtures/expected/`.**

---

## 7. What "done" looks like

### FTSE 100 non-financial (`company_a`, gate for M2.4 on local engines and M2.5 on both families)

- Every labelled cell in `company_a.json` matches exactly on value, period, page and unit scale, for **both** periods, or the difference is documented rounding in `labelling_notes.md`.
- The company-only balance sheet page is located, tagged `scope=company`, and never used.
- Adjusted or APM operating profit is present in the report but **not** chosen.
- All applicable arithmetic checks pass; `total_debt` is derived with `derived_from` (if OQ-2 is approved).
- Zero silent-wrong cells. The negative tests hold: remove the revenue row → null plus `missing_item`; perturb one engine's value → null or resolved `parser_disagreement`, never a silent pick.
- **No published value has method `llm_pointer`**, and no published value exists only because of the vision engine.
- Every published value's row, column and period were re-derived from the text layer (§5.1), not taken from an engine's claim.

### UK bank (`company_b`, gate for M8.1)

- Detected as `document_type: bank` by the §1.4 signals; `bank_layout` and `unclassified_balance_sheet` raised.
- `revenue`, `current_assets` and `current_liabilities` are **present and null by design**. All four corporate ratios have `value: null`, `reason: missing_input` (as `CLAUDE.md` requires) and **`applicability: not_applicable`**. The UI shows "Not applicable to banks" with the reason, **not** a number.
- Bank ids labelled in `company_b.json` match exactly, or are null with a warning.
- If OQ-4 = B, cost-to-income and loan-to-deposit are computed in code and CET1 and NIM are shown as cited reported metrics.
- `company_a` goldens still green.

### NHS trust (optional `company_c`)

- `public_sector_layout`; £000 detected; the statement of comprehensive income (SoCI) and statement of financial position (SoFP) located (the statement of changes in taxpayers' equity, SoCITE, is located but not extracted).
- Items mapped per the OQ-5 decision. Current ratio applicable; others as approved.

---

## 8. When a golden fails

Per the M2 prompt: **stop**, and write `docs/EXTRACTION_DEBUG_{company}.md` covering:
- the failing cell
- expected against extracted
- each engine's candidate and its anchoring result
- the page and a rendered crop path (`artifacts/debug/{company}/{item}_{period}.png`)
- the rule that fired
- a hypothesis
- the **smallest** proposed fix.

**Do not edit expected JSON** unless the tech lead confirms the label was wrong. **Do not generalise the parser** to fix one layout; add a targeted rule with a test.
