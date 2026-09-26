# OPEN QUESTIONS

Only questions whose answer **changes the architecture, the contracts or the milestone scope** are listed. Each has options, a recommendation, and the default that applies if it is left unanswered. Record the decision under each question (date and choice) before the milestone named in **Needed before**.

Per `CLAUDE.md`: where the question is an accounting one, both options are set out and the recommendation is **not** chosen for how it makes the demo look.

---

## OQ-1 — ROCE definition

**Needed before:** M3. Labelling is not blocked, because PLAN §7 labels a superset.

| | Option A — locked in `CLAUDE.md` | Option B — conventional UK textbook definition |
|---|---|---|
| Formula | `operating_profit / (total_equity + total_debt)` | `operating_profit / (total_assets − current_liabilities)` |
| Capital employed means | Financing view: equity plus interest-bearing debt (including leases where separately presented) | Balance-sheet view: long-term funding, which equals equity plus **all** non-current liabilities |
| Inputs | Depends on `total_debt`, which is usually derived from four lines (OQ-2) | Printed totals on almost every UK balance sheet (or non-current assets + current assets); some print "Total assets less current liabilities" directly |
| Includes | Current borrowings | Provisions, pension deficits, deferred tax (non-current) |
| Where it's taught | Common in credit and valuation practice (variants abound) | ACCA/CIMA and most UK undergraduate finance teaching |

- **Recommendation: B**, for two reasons:
  1. it is the definition an interviewer at a UK bank or NHS finance function is most likely to expect
  2. it has fewer derived inputs, so fewer ways to fail.
  Either definition is defensible. Whichever you choose, you must be able to explain it without notes (quality bar Q1).
- **If B:** you edit `CLAUDE.md` (it is locked; Claude Code must not) before M3, and `company_a.ratios.json` uses B as the locked value.
- **Default if unanswered:** A stays locked; B is computed only as an eval `alternatives` entry and never shown in the UI.

**Decision:** 2026-09-26: **B**, `operating_profit / (total_assets - current_liabilities)`. `CLAUDE.md` updated on the tech lead's instruction in the decisions commit.

---

## OQ-2 — How `total_debt` is recorded

**Needed before:** M0.

- **A. Derived value with provenance (schema v1.1.0 items 8–10).** Label and extract the four component lines. Code sums them and records `engine: "derived"` with `derived_from`. The rule from `CLAUDE.md` is applied exactly.
- **B. Stay on v1.0.0.** Publish `total_debt` only when it is printed as a single line; otherwise null + `missing_item`. For most FTSE reports this nulls D/E (and ROCE under OQ-1 A).
- **C. Sum in code without recording provenance.** Breaks auditability (`CLAUDE.md` rule 2).

**Also confirm (added at review):** "lease liabilities if separately present" is read as "separately presented **on the face** of the balance sheet" (SCHEMA §5). The alternative, face or notes, needs note extraction (v1.1).

**Recommendation: A, with the face-only reading.** **Default if unanswered:** B, which is honest but will null D/E for most companies.

**Decision:** 2026-09-26: **A**, with the face-only reading of "separately present".

---

## OQ-3 — Schema v1.1.0 tightening and optional fields

**Needed before:** M0.

SCHEMA §9 items 1–7, 9 and 11–14:
- `document_type`, `basis`, `pipeline_version`, `weeks`, `page_label`, `bbox`
- `page` and `raw_text` required when a value is present (1.1.0 only)
- new warning codes.

All are additive or conditional; every 1.0.0 pack stays valid.

- **A. Approve all.**
- **B. Approve a subset.** Name which.
- **C. Reject.** These facts then live only in the internal `ExtractionReport`; the UI cannot highlight cells or show group-vs-company basis from the pack.

**Recommendation: A.** **Default if unanswered:** C.

**Decision:** 2026-09-26: **A**, approve all. Schema v1.1.0 is applied as the first step of M0.

---

## OQ-4 — What v1 does for banks

**Needed before:** M8.1, and before labelling `company_b`.

- **A. Minimal.** Extract bank items; all four corporate ratios `applicability: not_applicable` (reason `missing_input`, per `CLAUDE.md`); no bank ratios.
- **B. Bank-literate.** A plus two ratios computed in code:
  - **cost-to-income** = `operating_expenses / total_income`, with operating expenses **excluding** credit impairment
  - **loan-to-deposit** = `loans_and_advances_to_customers / customer_deposits`.
  Plus **CET1 ratio** and **net interest margin** shown as `ReportedMetric` with citations, never computed: NIM needs average interest-earning assets, which the statements do not give.
  Our ratios may differ from the bank's reported (often adjusted) figures. The UI shows both and **never** "reconciles" them by adjusting inputs.
- **C. Defer banks to v1.1.** M8.1 uses an NHS trust or a second corporate instead.

**Recommendation: B.** It is one extra session (M8.2), and it shows exactly the bank-specific literacy that bank employers screen for. **You** add its two ratio definitions to the locked list in `CLAUDE.md` before M8.2. Claude Code must not.

**Default if unanswered:** A.

**Decision:** _________

---

## OQ-5 — NHS trust semantics (only if an NHS report is used in v1)

**Needed before:** M8.1.

- **A. Separate ids, few bridges.**
  - NHS canonical ids (SCHEMA §9).
  - Current ratio applies normally (the NHS statement of financial position separates current from non-current).
  - A **separately named** "operating surplus margin" = `operating_surplus_deficit / total_operating_income`, which **you** add to the locked list in `CLAUDE.md` before it is built.
  - D/E and ROCE: not applicable (public dividend capital and taxpayers' equity are not shareholder equity).
- **B. Bridge NHS lines into the locked ids** (total operating income → `revenue`; operating surplus → `operating_profit`; taxpayers' equity → `total_equity`; borrowings including PFI and leases → `total_debt`) so that all four locked ratios compute, flagged `public_sector_layout`. Risks presenting ratios whose meaning differs from the corporate case.
- **C. Defer NHS to v1.1.** Use a held-out second corporate as `company_c`.

**Recommendation: C for v1** (a cleaner generalisation test), **then A in v1.1.** Whether PFI and lease liabilities sit inside "Borrowings" on a given trust's statement of financial position must be checked on that trust's accounts before any mapping.

**Default if unanswered:** C.

**Decision:** _________

---

## OQ-6 — ESEF / iXBRL as an independent check

**Needed before:** M2.5 (option B) or v1.1 (option C).

Companies with securities on the UK regulated market (for example the LSE Main Market) file their annual financial report in ESEF format (XHTML with inline XBRL tags) to the FCA's National Storage Mechanism. Primary-statement figures are machine-tagged by the company itself.

- **A. Not in v1.**
- **B. Eval-only label check.** Download `company_a`'s ESEF filing. Compare the hand labels against tagged facts such as `ifrs-full:Revenue`, `ifrs-full:ProfitLossFromOperatingActivities`, `ifrs-full:CurrentAssets`, `ifrs-full:CurrentLiabilities`, `ifrs-full:Equity`, `ifrs-full:Assets`, and the lease-liability concepts. Mismatches go to the labelling notes. No runtime change.
- **C. Runtime verifier (v1.1).** Optional companion iXBRL upload, parsed with an XBRL processor. The tagged facts become a **fourth, authoritative-where-available** vote.
  - Caveats: filers use extension elements; `decimals`, `scale` and `sign` attributes must be honoured; AIM companies and NHS trusts are not covered.

**Recommendation: B now, C in v1.1.** B costs about an hour and strengthens the goldens that everything else is measured against.

**Default if unanswered:** A.

**Decision:** _________

---

## OQ-7 — Scope of the premium parse

**Needed before:** M1.

- **A. Whole document** (about $2 per 200-page report). Azure DI's reading order and paragraph roles also improve narrative chunking.
- **B. Statement pages only** (about $0.08). Narrative reading order comes from PyMuPDF plus column heuristics.

**Recommendation: A for the goldens and the demo, with B as a configuration flag.** Measure the retrieval difference at M4.2 (E3 under A against B) and record it. This is a cost-for-quality trade-off, not a correctness one: numbers are anchored either way.

**Default if unanswered:** A.

**Decision:** _________

---

## OQ-8 — Hosting and uploads

**Needed before:** M6.2.

- **A. Local only.**
- **B. Hosted demo:**
  - precomputed goldens public and read-only
  - uploads behind a shared password with a daily cap
  - originals deleted after 30 days
  - Supabase London (Postgres, pgvector and Storage); frontend on Vercel; API and worker on a scale-to-zero container host.
- **C. Public uploads.** Not recommended: cost abuse, plus the data-handling obligations that come with arbitrary documents.

**Recommendation (changed at review): A for all of v1; B is v1.1.** The quality bar asks for local reproducibility, not hosting, so hosting in v1 was hidden scope. **Default if unanswered:** A.

**Decision:** _________

---

## OQ-9 — Default LLM provider

**Needed before:** M2.4 (first LLM call: the review-only mapping suggestion).

- **A. Anthropic.** Claude Opus 5.5 for number-blind mapping and the vision vote; Claude Sonnet 5 for commentary (Haiku 4.5 for the lean configuration).
- **B. Google Gemini.** The original project brief named Gemini 1.5 Flash, which has since been superseded; any current Gemini model would be used through the same adapter.

Both sit behind the `llm/` adapter. The choice affects structured-output handling, image input for the vision vote, and the per-report cost in COST_AND_OPS. Model ids are configuration.

**Recommendation: A as default, with the B adapter kept optional.** **Default if unanswered:** A.

**Decision:** _________

---

## OQ-10 — Commit small golden excerpts so CI can run the extraction goldens (added at review)

**Needed before:** M2.4.

The PDFs and `artifacts/` are git-ignored, so CI has no inputs for E1 (EVAL §2).

- **A. Commit excerpts.** `tests/golden/{company}/` holds the text-layer JSON of the **located statement pages only**, recorded Azure DI responses for those pages, and the expected files. That is a few kilobytes of a public document (ADR-009).
- **B. No excerpts.** E1 runs only locally (`make eval`); CI runs the synthetic suite (E7) and unit tests.

**Recommendation: A.** The excerpts are small, public and essential for regression safety. Revisit if the repository is made public and any issuer objects. **Default if unanswered:** B.

**Decision:** 2026-09-26: **A**, commit statement-page excerpts to `tests/golden/`.

---

## OQ-11 — Equity basis for D/E and ROCE (added at review)

**Needed before:** M3. Label both lines now (PLAN §7.2), so this does not block labelling.

- **A. Total equity including non-controlling interests** (current SCHEMA §5). The numerator (group debt) and denominator cover the same consolidated group.
- **B. Equity attributable to owners of the parent.** Closer to what shareholders own; mismatched with group-level debt when NCI is material.

For most FTSE 100 groups, NCI is small and the two differ only slightly. For groups with large minority stakes, the difference is material.

**Recommendation: A.** **Default if unanswered:** A (already the SCHEMA rule), with `equity_attributable_to_owners` labelled for reference.

**Decision:** 2026-09-26: **A**, include non-controlling interests. With OQ-1 = B, this affects debt-to-equity only.
