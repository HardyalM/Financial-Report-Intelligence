# SCHEMA — StatementPack and related contracts

`schemas/statement_pack.schema.json` (v1.0.0) is the **locked numeric contract**. This document explains it field by field, sets the conventions every engine and every human labeller must follow, and proposes a **backwards-compatible v1.1.0** that closes the gaps found during planning.

**Nothing in §9 is applied yet.** It needs tech-lead approval ([OQ-2, OQ-3](OPEN_QUESTIONS.md)). Locked ratio field names are unchanged throughout.

---

## 1. Lock policy

- The JSON Schema is canonical ([ADR-006](ARCHITECTURE.md#adr-006--json-schema-is-the-source-of-truth-for-contracts)). Pydantic and TypeScript types are generated from it; CI fails on drift.
- A schema change needs a version change in `schema_version`, a note in `docs/ARCHITECTURE.md` (ADR section) and green golden tests.
- **Additive, optional** fields bump the minor version. Anything that would make an existing valid pack invalid bumps the major version and is out of scope for v1.
- The locked ratio inputs are `revenue`, `operating_profit`, `current_assets`, `current_liabilities`, `total_equity` and `total_debt`. They are never renamed.

---

## 2. Top-level fields (v1.0.0)

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | `"1.0.0"` | Contract version |
| `company_name` | string or null | As printed on the cover or statements; null if not confidently found |
| `source.filename` | string | Original upload filename |
| `source.page_count` | int ≥ 1 | PDF page count |
| `source.parser_engines` | string[] | Engines that **ran** for this pack (not only those that agreed) |
| `currency` | ISO 4217, 3 letters | Presentation currency of the primary statements (`GBP`, `USD`, `EUR`) |
| `unit_scale` | 1, 1000 or 1,000,000 | Scale of every `value` in the pack. **Pack-level**: all published values share it. |
| `periods[]` | array | Reporting periods present in the statements (see §8) |
| `items{}` | map canonical id → `line_item` | Canonical line items. Items the ratios need **must be present even when null**. |
| `warnings[]` | array | Structured warnings (§10). Warnings are part of the product, not debug output. |

### `line_item`

| Field | Meaning |
|---|---|
| `id` | Canonical id; equals the map key |
| `label_found` | Row label as printed (normalised whitespace), for example "Total current liabilities" |
| `statement` | `income_statement`, `balance_sheet`, `other` or null |
| `values[]` | One `period_value` per period |

### `period_value`

| Field | Meaning |
|---|---|
| `period_id` | References `periods[].id` |
| `value` | Number in `unit_scale`, sign-normalised (§4.2), or **null** |
| `page` | 1-based **PDF page index** (§4.1) |
| `raw_text` | Printed token(s) exactly as on the page, for example `"(1,234.5)"` |
| `confidence` | 0–1 publication confidence (§4.5). Hand labels are 1.0. |
| `engine` | Provenance (§4.6) |

---

## 3. What the v1.0.0 schema does not yet capture

Found during planning. Each has a proposed fix in §9.

1. **`total_debt` is rarely one printed figure.** It is usually borrowings (current + non-current) plus lease liabilities (current + non-current): up to four printed cells. v1.0.0 has nowhere to record that a value was **derived** or from which cells.
2. **`page` and `raw_text` are optional**, although `CLAUDE.md` rule 2 requires them for every numeric fact.
3. There is **no document type** (corporate, bank or NHS) and **no basis** (consolidated or company-only), although both change how mapping and ratios behave.
4. There is **no printed page label**. The PDF page index and the printed folio differ in almost every annual report, and reviewers think in folios.
5. There is **no bounding box**, so the UI cannot highlight the exact cell.
6. The warning codes miss several failure modes the design depends on (for example `arithmetic_check_failed` and `entity_scope_ambiguous`).
7. There is no `pipeline_version` on the pack, so a pack cannot be traced to the code that produced it.
8. There is no `note_ref` on a line item, so the link from a statement line to its note is lost. *(Found at review.)*
9. There is no record of whether the balance sheet is classified, which is what decides current-ratio applicability. *(Found at review.)*

---

## 4. Conventions every labeller and every engine must follow

### 4.1 Page

`page` = **1-based physical page index in the PDF file**, which is what a PDF viewer shows as "page X of Y". It is **not** the number printed on the page. For two-page spreads (one PDF page holding two printed pages), `page` is still the PDF page. Proposed `page_label` (§9) carries the printed folio when the PDF defines page labels.

### 4.2 Value and sign

`value` is the number **as printed**, in the pack's `unit_scale`. It is not multiplied out: `£13,907.5m` becomes `13907.5` with `unit_scale: 1000000`. The sign is normalised to each item's **canonical orientation**:

| Item kind | Canonical sign |
|---|---|
| Revenue, income | Positive |
| Profit lines (`operating_profit`, `profit_before_tax`, `net_income`) | Positive = profit, negative = loss |
| Assets (`current_assets`, `total_assets`, `cash`, `non_current_assets`) | Positive |
| Liabilities (`current_liabilities`, `total_liabilities`, `borrowings_*`, `lease_liabilities_*`, `total_debt`) | **Positive magnitude, even when printed in brackets** |
| `total_equity`, `net_current_assets` | Signed (negative equity is negative) |

Printed conventions:
- `(1,234)` is negative as printed.
- `–`, `-`, `—` or `nil` means **0**.
- Unicode minus is normalised.
- Footnote markers (`*`, `†`, superscripts) are stripped from the value and kept in `raw_text`.

### 4.3 `raw_text`

Exactly the printed characters for the cell, with whitespace collapsed. Anchoring ([EXTRACTION §5.1](EXTRACTION.md)) matches on a normalised form (commas, spaces and bracket/minus styles unified), but the stored `raw_text` is verbatim.

### 4.4 Unit scale and currency

See §7.

### 4.5 Confidence

A **publication confidence**, computed deterministically from the mapping method, engine agreement and arithmetic checks ([EXTRACTION §5.3](EXTRACTION.md)). It is not a model's self-reported probability.
- A value is published only if `confidence ≥ τ` (default τ = 0.80, calibrated on the goldens).
- Below τ, `value` is **null**, and the best candidate appears in the review queue, not in the pack.

### 4.6 Engine vocabulary

| `engine` | Meaning |
|---|---|
| `pdfplumber`, `pymupdf_tables`, `azure_di` (v1); `reducto`, `llamaparse`, `docling` (v1.1) | Value from one engine family (other families absent or silent) |
| `vision:<model_id>` | Never on a published value alone. Vision only votes. |
| `reconciled` | Anchored engines from two or more **families** agreed; details in `ExtractionReport` |
| `derived` | Computed in code from other items (proposed §9, for example `total_debt`) |
| `hand` | Golden label. Only in `fixtures/expected/`. |
| `human_override` | Set via the review API; audit record in the `overrides` table |

---

## 5. Canonical line items for v1

| Id | Statement | Definition | Typical printed labels | Never map from |
|---|---|---|---|---|
| `revenue` | Income statement | Statutory revenue of the group | Revenue; Group revenue; Total revenue; Turnover; Revenue from contracts with customers | Adjusted / underlying revenue; sales including concessions; gross transaction value; "Total income" (bank) |
| `operating_profit` | Income statement | Statutory operating profit or loss on the face of the income statement | Operating profit; Operating profit/(loss); Group operating profit; Profit from operations | Adjusted / underlying operating profit; profit before adjusting items; trading profit; EBITDA; headline profit |
| `profit_before_tax` | Income statement | Statutory profit before tax | Profit before tax(ation); Profit/(loss) before taxation | Adjusted PBT; PBT before adjusting items |
| `net_income` | Income statement | Profit for the year, total (owners + non-controlling interests) | Profit for the year; Profit for the financial year | Profit attributable to owners of the parent (a separate item if needed) |
| `current_assets` | Balance sheet | Total current assets | Total current assets; an unlabelled subtotal under "Current assets" | Net current assets |
| `current_liabilities` | Balance sheet | Total current liabilities | Total current liabilities; "Creditors: amounts falling due within one year" (Companies Act formats) | Net current liabilities |
| `total_assets` | Balance sheet | Total assets | Total assets | "Total assets less current liabilities" (a separate proposed item) |
| `total_equity` | Balance sheet | Total equity **including** non-controlling interests | Total equity; Total shareholders' equity (when no NCI line follows) | Equity attributable to owners of the parent |
| `total_debt` | Balance sheet (derived) | Per `CLAUDE.md`: interest-bearing borrowings + lease liabilities if separately present, else borrowings only + warning | Rarely printed as one line; normally derived (§9) | Trade payables; derivative liabilities; provisions; pension deficits |
| `cash` | Balance sheet | Cash and cash equivalents on the face | Cash and cash equivalents; Cash and short-term deposits | Restricted cash shown separately; cash in a cash flow statement |

**`total_debt` resolution rule (v1):**
1. Take borrowings from the face of the balance sheet (current + non-current).
2. Add lease liabilities if they are presented as **separate lines on the face** (current + non-current).
3. If leases are not separately presented, use borrowings only and raise `lease_not_separately_presented` (proposed). The note may show leases sitting inside "borrowings", in which case nothing is missing, but v1 does not read notes for numbers.
4. Bank overdrafts count as borrowings when presented within or beside them.
5. **Presence semantics** (added at review; implemented in EXTRACTION §5.4a):
   - A component whose row **exists but is unresolved** (null) makes `total_debt` **null**. It never falls back to "borrowings only".
   - A component counts as **zero** only when no row matches it **and** the section's subtotal check passed, which proves every row in that section was seen.
6. This is written down so the labeller and the code apply the **same** rule. Any divergence is a labelling note, not a code change.

**Interpretations of `CLAUDE.md` made here (flagged, not silently chosen):**
- "Separately present" is read as "separately presented **on the face** of the balance sheet", because v1 does not read notes for numbers. The alternative (face or notes) needs note extraction, which is v1.1. Confirm under [OQ-2](OPEN_QUESTIONS.md).
- `total_equity` **includes** non-controlling interests, so that the denominator covers the same group whose debt is in the numerator. The alternative (equity attributable to owners) is [OQ-11](OPEN_QUESTIONS.md).

---

## 6. Alias map approach

The alias map is **configuration, not code**. It lives in `finintel/mapping/aliases/{corporate,bank,nhs_trust}.yaml` and is loaded according to the detected document type.

Each entry has:
- **canonical id**
- **statement** it may come from
- **section context**: the heading the row must sit under, for example "Current liabilities"
- **include patterns**: normalised exact strings first, then anchored regular expressions
- **exclude patterns**: the "never map from" column above
- **style preference**: prefer rows styled as totals (bold, or ruled above or below)

Illustrative shape (not final content):

```yaml
operating_profit:
  statement: income_statement
  include_exact: ["operating profit", "operating profit/(loss)", "group operating profit", "profit from operations"]
  include_regex: ["^operating (profit|\\(loss\\))(/\\(loss\\)|/profit)?$"]
  exclude_any: ["adjusted", "underlying", "before adjusting items", "before exceptional", "pre-exceptional", "trading profit", "headline", "ebitda"]
  prefer_total_style: true
```

**Label normalisation, before matching:**
- lowercase and Unicode NFKC
- strip note references, "(note 12)" and footnote markers
- "&" becomes "and"
- collapse whitespace
- drop trailing colons
- **Multi-line labels** are joined first. Wrapped labels are common in narrow label columns.

**Precedence:**
1. Exact normalised alias with the correct section context
2. Regex alias
3. **Structural rule**, for example the unlabelled subtotal row directly after the last row under "Current assets", whose value equals the sum of the rows above within tolerance
4. Number-blind LLM pointer ([EXTRACTION §4.4](EXTRACTION.md))

**Conflicts:** if two rows match one canonical id at the same precedence, prefer the total-styled row within the correct section. If still tied, raise `alias_weak`; the value is null and both candidates go to review.

---

## 7. `unit_scale` and currency rules

| Printed header token(s) | `currency` | `unit_scale` |
|---|---|---|
| `£m`, `£ m`, `£ million`, `£ millions`, `£mn` | GBP | 1,000,000 |
| `£'000`, `£000`, `£ thousand`, `£k` | GBP | 1,000 |
| `£` alone (an explicit statement that figures are in pounds) | GBP | 1 |
| `$m`, `US$m`, `US$ million`, `$ millions` | USD | 1,000,000 |
| `$'000`, `US$000` | USD | 1,000 |
| `€m`, `€ million`, `EURm` | EUR | 1,000,000 |
| `€'000` | EUR | 1,000 |

Rules:
1. Search the statement's column-header band and title block for exactly **one** unit token per statement.
2. The income statement and balance sheet must agree. Disagreement or absence means `unit_ambiguous`, and **the pipeline blocks** with status `needs_unit_confirmation`. There is no default and no guess.
3. Tokens in notes pages never set the pack's unit.
4. `$` alone is treated as USD only with an explicit "US" or a narrative statement of presentation currency. Otherwise `currency_ambiguous` (proposed) also blocks.
5. A narrative magnitude cross-check ("revenue of £13.9bn" against 13,907.5 at £m) produces a warning only, never a correction.

---

## 8. Periods and comparative columns

- **Period id:** `FY` + calendar year of the period end date (`FY2025` for the 52 weeks ended 29 March 2025). **Label:** as printed. **`end_date`:** ISO date from the column header or statement title ("for the year ended…" / "as at…").
- **Duration and instant:** the income statement's `FY2025` (year ended X) and the balance sheet's `FY2025` (as at X) share one id, because they share the end date.
- **Column order:** determined by the parsed dates, never by position (current first is only usual, not guaranteed).
- **Columnar income statements** (for example "Before adjusting items | Adjusting items | Total"): only the **Total/Statutory** column is a v1 value column. If the classifier cannot identify it, raise `period_ambiguous` (proposed) and the values are null.
- **Restated comparatives:** "Restated", "(restated)" or a restatement footnote marker on the header gives `is_restated: true` plus a `restated_comparative` warning. The restated figure is used (it is the current basis).
- **More than two periods** (rare on the face): keep all, ratios for each.
- **52/53 weeks:** proposed optional `weeks` field. The UI shows a note when the periods differ in length.

---

## 9. Proposed v1.1.0 extension (backwards-compatible)

**Status: proposal. Needs approval ([OQ-2, OQ-3](OPEN_QUESTIONS.md)).** Every change is additive or conditional on `schema_version == "1.1.0"`, so every valid 1.0.0 pack (including `EXAMPLE_company_a.json`) remains valid.

| # | Change | Why |
|---|---|---|
| 1 | `schema_version`: `const "1.0.0"` → `enum ["1.0.0", "1.1.0"]` | Allow both |
| 2 | Top-level optional `document_type`: `corporate` / `bank` / `nhs_trust` / `other` | Drives alias map and ratio applicability |
| 3 | Top-level optional `basis`: `consolidated` / `company_only` / `single_entity` | Makes the group-vs-company decision explicit and testable |
| 4 | `source.sha256`, `source.pipeline_version` (optional strings) | Traceability |
| 5 | `periods[].weeks` (optional integer), `periods[].start_date` (optional) | 52/53-week years |
| 6 | `period_value.page_label` (optional string or null) | Printed folio for reviewers |
| 7 | `period_value.bbox` (optional `[x0, y0, x1, y1]` in PDF points, or null) | Exact cell highlight in the UI |
| 8 | `period_value.derived_from` (optional array of `{item, period_id}`) + `derivation` (`"sum"`) | Records **how** `total_debt` was built. No hidden arithmetic. |
| 9 | Conditional rule (only when `schema_version == "1.1.0"`): if `value` is not null and `engine` is not `derived`, then `page` and `raw_text` are **required and non-null**; if `engine == "derived"`, then `derived_from` is required | Enforces `CLAUDE.md` rule 2 in the schema itself |
| 10 | New documented canonical ids (already allowed via `additionalProperties`): `borrowings_current`, `borrowings_non_current`, `lease_liabilities_current`, `lease_liabilities_non_current`, `total_liabilities`, `non_current_assets`, `net_current_assets`, `total_assets_less_current_liabilities`, `equity_attributable_to_owners`, `non_controlling_interests` | Components for `total_debt`; inputs to arithmetic checks; optional ROCE inputs ([OQ-1](OPEN_QUESTIONS.md)) |
| 11 | Warning codes added (below) | Failure modes the design relies on |
| 12 | `line_item.note_ref` (optional string or null), for example `"22"` or `"22.1"`, copied from the statement's notes column (added at review) | Lets the UI link "Borrowings, note 22" to the note's narrative chunks. The first draft read note references and then dropped them. |
| 13 | Top-level optional `balance_sheet_classified` (boolean) (added at review) | Records the EXTRACTION §1.4 test that drives current-ratio applicability |
| 14 | `derived_from[]` entries may carry `assumed_zero: true` (added at review) | Makes the "absent component counted as zero" decision visible and auditable |

### Bank ids (M8.1; subject to OQ-4)

`total_income`, `net_interest_income`, `operating_expenses`, `impairment_charge`, `loans_and_advances_to_customers`, `customer_deposits`, together with the existing `profit_before_tax`, `total_assets`, `total_liabilities` and `total_equity`.

For banks:
- `revenue`, `current_assets` and `current_liabilities` are **present and null** with `bank_layout` and `unclassified_balance_sheet`.
- They are **not** mapped from "Total income" or liquidity-ordered lines.

### NHS trust ids (M8.1 optional, or v1.1; subject to OQ-5)

`total_operating_income`, `operating_expenses`, `operating_surplus_deficit`, `surplus_deficit_for_year`, `total_taxpayers_equity`, `public_dividend_capital`, `pfi_liabilities_current`, `pfi_liabilities_non_current`.

NHS statements of financial position **do** split current and non-current, so `current_assets` and `current_liabilities` map normally, with `public_sector_layout`.

---

## 10. Warning codes

| Code | Status | Severity | Raised when |
|---|---|---|---|
| `missing_item` | existing | warning | A canonical item required by ratios was not found |
| `low_confidence` | existing | warning | Best candidate below τ, so the value is null |
| `parser_disagreement` | existing | warning | Anchored engines disagree. The message says resolved (value kept, capped confidence) or unresolved (null). |
| `unit_ambiguous` | existing | **blocking** | Zero or conflicting unit tokens |
| `sign_ambiguous` | existing | warning | Sign evidence conflicts after section context and arithmetic checks |
| `multi_page_table` | existing | info | Statement spans pages or a spread |
| `restated_comparative` | existing | info | Comparative column is restated |
| `alias_weak` | existing | warning | Only a weak or ambiguous label match |
| `bank_layout` | existing | info | Bank document type detected; corporate items null by design |
| `public_sector_layout` | existing | info | NHS or public-sector layout detected |
| `arithmetic_check_failed` | proposed | warning | A subtotal or identity check failed beyond rounding tolerance |
| `entity_scope_ambiguous` | proposed | warning | Cannot tell group from company statement |
| `period_ambiguous` | proposed | warning | Period or statutory column cannot be identified |
| `currency_ambiguous` | proposed | **blocking** | Currency cannot be determined |
| `not_digitally_born` | proposed | warning | Text layer missing or sparse; OCR-only values are capped below τ |
| `lease_not_separately_presented` | proposed | warning | `total_debt` = borrowings only |
| `derived_value` | proposed | info | A published value was derived in code (with `derived_from`) |
| `human_override` | proposed | info | A value was set or accepted by a reviewer |
| `human_override_unanchored` | proposed (review) | warning | A reviewer forced a value that is not in the page's text layer. A persistent amber badge is shown. |
| `unit_confirmed_manually` | proposed (review) | warning | Unit or currency was set by a reviewer. A persistent badge is shown. |
| `unclassified_balance_sheet` | proposed (review) | info | No current/non-current split, so `current_assets` and `current_liabilities` are null by design |
| `document_type_ambiguous` | proposed (review) | **blocking for ratios** | Document profile unclear; corporate ratios withheld until a reviewer sets the type |
| `reduced_verification` | proposed (review) | info | Only one engine family produced candidates (for example Azure unavailable); the UI shows a banner |

---

## 11. Related contracts introduced by later milestones

New schema files. They never modify `statement_pack.schema.json`.

| File | Milestone | Content |
|---|---|---|
| `schemas/ratio_pack.schema.json` | M3 | `statement_pack_sha`; `formulas_locked: true`. Per period and per ratio:<br>• `value` or null<br>• `status`<br>• `reason`: `missing_input` whenever an input is null, **exactly as `CLAUDE.md` says**; `division_by_zero` otherwise where it applies<br>• **`applicability`** (`applicable` / `not_applicable` / `withheld`) with an `explanation` (ADR-008)<br>• `missing_inputs[]` naming each null input<br>• `flags` (for example `negative_denominator`, shown **beside** the value, never instead of it)<br>• `formula` (verbatim from `CLAUDE.md`)<br>• `inputs` (each `{value, item, period_id, page, badges[]}`)<br>Plus `changes`: margin-type ratios in percentage points, other ratios as absolute differences, line items as absolute and percentage change, all computed in code. |
| `schemas/citation.schema.json` | M5.1 | `{citation_id, chunk_id, quote, page, page_label, char_start, char_end, section, heading_path, note_number, bbox[], match: "exact" or "normalised"}`. The page fields are **always code-derived**. |
| `schemas/commentary.schema.json` | M5.1 | Topics → paragraphs `{template, rendered, citations[], validation}`; `executive_summary`; model, prompt version, retrieval set id, trace id; `disclaimer`. See [RAG §4](RAG.md). |
| `schemas/reported_metric.schema.json` | M8.2 (if OQ-4 = B) | `{id, label_found, value_text, value, unit, period_id, page, quote, chunk_id}`.<br>• **`value_text` must be a verified verbatim substring of `quote`**, which is itself verified against the chunk, exactly as for citations.<br>• `value` is parsed from `value_text` **by code**.<br>• Candidates are found by deterministic patterns (for example `CET1 ratio (of)? ([0-9.]+) ?(%\|per cent)`) over retrieved chunks. A model may *propose* a chunk but never supplies the value.<br>• Displayed "as reported (p. X)", **never** used in computation. |
| `ExtractionReport` (internal, not locked) | M2.5 | Per item and period: every engine's candidate, anchoring result, checks run, decision and reason |

Expected-fixture formats are defined in [EVAL §3](EVAL.md).
