# RESULTS

What the pipeline measured, and nothing else. Every number below is a field of the eval report it
cites: the run id names the company, the time (UTC) and the code commit, and the report is kept in
[`results/`](results/) (a copy of `artifacts/eval/{run_id}/report.json`). `python
scripts/check_results.py` fails if any number here does not equal a cited field.

These are **case studies, not accuracy rates** ([EVAL, Principles](EVAL.md)). company_a and company_b are
**development goldens**: their labels were used while building, so they show the pipeline doing
what it was built to do on them, not how it generalises. The held-out report, scored once, is
below, and it went badly.

## Runs cited

| Run | What it covers |
|---|---|
| `company_a-20261003T011619Z-01552f5` | company_a (a large UK-listed consumer goods group): E1, E2, E3, E6, and the M5.2 commentary run (Gemini, recorded) replayed offline for E4, E8, QA-20 and the human ratings |
| `company_b-20261003T011630Z-01552f5` | company_b (UK bank): E1, E2, E6, ratio applicability and the label's absent items |

Both runs used the local table engines only (Azure Document Intelligence did not run: no key), so
every figure was read by one engine family and checked by arithmetic, not by a second reader.

## Figures: E1 (every labelled cell, both periods)

| Report | Labelled cells | Matched exactly | Honest null | Silent wrong | Unit errors | Cited |
|---|---|---|---|---|---|---|
| company_a | 22 | 22 | 0 | 0 | 0 | `company_a-20261003T011619Z-01552f5`: e1.labelled, e1.matched, e1.honest_null, e1.silent_wrong, e1.unit_errors |
| company_b | 28 | 28 | 0 | 0 | 0 | `company_b-20261003T011630Z-01552f5`: e1.labelled, e1.matched, e1.honest_null, e1.silent_wrong, e1.unit_errors |

"Matched exactly" means value, period, page and printed text all equal the hand label. A silent
wrong cell is a confident wrong number; there were none.

No published figure came from a model's row pointer, or from a vision reading alone:

| Report | Published from a model pointer | Published on vision alone | Cited |
|---|---|---|---|
| company_a | 0 | 0 | `company_a-20261003T011619Z-01552f5`: e6.published_llm_pointer, e6.published_vision_only |
| company_b | 0 | 0 | `company_b-20261003T011630Z-01552f5`: e6.published_llm_pointer, e6.published_vision_only |

## Ratios: E2 (computed in code, against hand-computed values)

| Report | Ratio cells expected | Matched from the extracted pack and from the labels | Tolerance | Cited |
|---|---|---|---|---|
| company_a | 8 | 8 | 1e-09 | `company_a-20261003T011619Z-01552f5`: e2.expected, e2.matched, e2.tolerance |
| company_b | 4 | 4 | 1e-09 | `company_b-20261003T011630Z-01552f5`: e2.expected, e2.matched, e2.tolerance |

company_a's debt-to-equity is null in both periods by design (the balance sheet shows only
"financial liabilities", from which borrowings cannot be isolated), and the hand-computed file
expects exactly that.

For the bank, the four corporate ratios are not applicable, none of them is computed, and none of
the lines the label marks absent (revenue, operating profit, current assets, current liabilities,
total debt) was published:

| Check | Value | Cited |
|---|---|---|
| Corporate ratios not applicable | 4 | `company_b-20261003T011630Z-01552f5`: ratios.not_applicable |
| Corporate ratio values computed | 0 | `company_b-20261003T011630Z-01552f5`: ratios.computed |
| Absent lines labelled / published | 5 / 0 | `company_b-20261003T011630Z-01552f5`: absent.labelled, absent.published |

The bank's cost-to-income and loan-to-deposit are the E2 cells above. Its CET1 ratio and net
interest margin are shown as the bank states them, quoted with the page, and are not part of any
eval number here.

## Retrieval: E3 (company_a)

| Labelled questions | Found within the first eight results | Cited |
|---|---|---|
| 5 | 4 | `company_a-20261003T011619Z-01552f5`: e3.queries, e3.hits |

## Commentary (company_a)

The commentary is the recorded M5.2 run (Gemini, generated mode), replayed offline with the same
inputs, so the numbers are reproducible without the model.

What reached the screen, after validation:

| Displayed | Count | Cited |
|---|---|---|
| Paragraphs and bullets | 29 | `company_a-20261003T011619Z-01552f5`: e4.displayed_paragraphs |
| Citations that could not be verified | 0 | `company_a-20261003T011619Z-01552f5`: e4.displayed_unverified_citations |
| Numbers not written by code or inside a verified quote | 0 | `company_a-20261003T011619Z-01552f5`: e4.displayed_naked_numbers |
| Advice language | 0 | `company_a-20261003T011619Z-01552f5`: e4.displayed_advice |
| Figures without a source page | 0 | `company_a-20261003T011619Z-01552f5`: e4.displayed_figures_without_source |

What the validators caught before display, across the model calls:

| Caught | Count | Cited |
|---|---|---|
| Model calls | 4 | `company_a-20261003T011619Z-01552f5`: e4.pre_validation.calls |
| Fabricated or out-of-set quotes | 1 | `company_a-20261003T011619Z-01552f5`: e4.pre_validation.fabricated_or_out_of_set_quotes |
| Numbers typed by the model | 2 | `company_a-20261003T011619Z-01552f5`: e4.pre_validation.naked_number_violations |
| Quoted text that was not cited | 1 | `company_a-20261003T011619Z-01552f5`: e4.pre_validation.unverified_quote_violations |
| Paragraphs without a citation | 1 | `company_a-20261003T011619Z-01552f5`: e4.pre_validation.paragraphs_without_citation |

Coverage against the tech lead's labels (E8) and the twenty questions (QA-20):

| Check | Result | Cited |
|---|---|---|
| Principal risks covered | 13 of 14 | `company_a-20261003T011619Z-01552f5`: e8.risks.found, e8.risks.total |
| Key audit matters covered | 3 of 3 | `company_a-20261003T011619Z-01552f5`: e8.kams.found, e8.kams.total |
| QA-20 answered correctly | 18 of 20 | `company_a-20261003T011619Z-01552f5`: qa.passed, qa.total |

The missing risk is "Customer and channel": the model's quote for it was not verbatim, so code
removed the paragraph rather than show an unverified quote. The going-concern statement was
reported correctly. The two QA failures: `v2` (how the company describes its strategy) produced no
answer that passed validation, and `v3` (what the chief executive said about the year's
performance) was answered from the right page but did not mention underlying sales or volume.

Human rating: the tech lead, one rater, one judgement per displayed paragraph (not per atomic
claim, as the [EVAL protocol](EVAL.md) proposes), recorded in `fixtures/expected/ratings.json` as two
yes/no answers, "faithful" (the paragraph says what its cited quotes say) and "cited" (the
citations point at the right place). The scorer counts a paragraph as supported only when both are
yes. The file has no "contradicted" option, so no contradiction count is reported.

| Paragraphs rated | Faithful and cited | Not | Cited |
|---|---|---|---|
| 29 | 27 | 2 | `company_a-20261003T011619Z-01552f5`: ratings.total, ratings.supported_count, ratings.unsupported_count |

Both paragraphs answered no to both questions. They are executive-summary bullets
(`executive_summary:1` and `executive_summary:3`) whose sentences claim more than the quotes they
cite.

## Held-out report (company_c)

Tesco PLC, its latest annual report (see `fixtures/pdfs/SOURCES.md`). Kept out of every test and
inspector run, labelled by the tech lead, then scored **once**. Nothing was changed to improve
this result; any fix made from now on makes company_c a development golden, and this section will
say so. Local engines only; no hand-computed ratios, so E2 was not run (EVAL, Target scores).

| Labelled cells | Matched exactly | Honest null | Silent wrong | Unit errors | Cited |
|---|---|---|---|---|---|
| 14 | 0 | 10 | 4 | 0 | `company_c-20261010T225313Z-e965d82`: e1.labelled, e1.matched, e1.honest_null, e1.silent_wrong, e1.unit_errors |

**The pipeline failed this report.** It read no labelled figure correctly, and it showed two
confident wrong numbers, which is the failure this project exists to prevent.

Every miss:

| Line | Year | Labelled | Shown | Why | Cited |
|---|---|---|---|---|---|
| Revenue | FY2025 | 69,916 | 0 | **Silent wrong.** The income statement has three columns per year (before adjusting items, adjusting items, total). The period header gave the year to the adjusting-items column, which prints "–" for revenue, read as zero. | `company_c-20261010T225313Z-e965d82`: e1.cells.0.expected, e1.cells.0.got |
| Operating profit | FY2025 | 2,711 | -417 | **Silent wrong.** Same wrong column: the adjusting items, not the statutory total. | `company_c-20261010T225313Z-e965d82`: e1.cells.2.expected, e1.cells.2.got |
| Revenue | FY2024 | 68,187 | empty | **Silent wrong as scored.** Five candidate columns and none clearly the total, so the year was correctly left empty, but the reason was recorded against the statement, not the line, so the line carries no warning. | `company_c-20261010T225313Z-e965d82`: e1.cells.1.expected |
| Operating profit | FY2024 | 2,821 | empty | As revenue FY2024. | `company_c-20261010T225313Z-e965d82`: e1.cells.3.expected |
| Current assets | both | 8,856 / 16,606 | empty | Honest null. The balance sheet has two columns per year with the same heading, so no column could be chosen; flagged. | `company_c-20261010T225313Z-e965d82`: e1.cells.4.expected, e1.cells.5.expected |
| Current liabilities | both | 13,820 / 13,350 | empty | Honest null, same cause. | `company_c-20261010T225313Z-e965d82`: e1.cells.6.expected, e1.cells.7.expected |
| Total assets | both | 38,890 / 47,039 | empty | Honest null, same cause. | `company_c-20261010T225313Z-e965d82`: e1.cells.8.expected, e1.cells.9.expected |
| Total equity | both | 11,662 / 11,665 | empty | Honest null, same cause. | `company_c-20261010T225313Z-e965d82`: e1.cells.10.expected, e1.cells.11.expected |
| Total debt | both | 14,666 / 15,341 | empty | Honest null, same cause. | `company_c-20261010T225313Z-e965d82`: e1.cells.12.expected, e1.cells.13.expected |

Also wrong on this report: the balance-sheet lines carry a second warning, "no alias map for
document type corporate yet", which is false (the corporate map exists; the statement had no
usable period). Labelled lines not shown here were not labelled.

What this says: the column and period logic was built against two layouts and does not yet handle
a statement that prints adjusting items as separate columns, or a balance sheet whose two columns
per year share a heading. The arithmetic checks did not catch the wrong column, because no check
covers revenue or a lone operating-profit figure. These are the first things to fix, each with a
regression test, after which company_c counts as a development golden.

## What these results do not show

- How the pipeline does on reports it was not built against: that is what the held-out run is for.
- Agreement between two independent table engines: only one engine family ran.
- Commentary quality beyond one company, one model and one rater.
- Anything about NHS trusts, insurers or scanned PDFs, which are not supported.
