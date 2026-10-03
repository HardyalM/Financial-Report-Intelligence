# RESULTS

What the pipeline measured, and nothing else. Every number below is a field of the eval report it
cites: the run id names the company, the time (UTC) and the code commit, and the report is kept in
[`results/`](results/) (a copy of `artifacts/eval/{run_id}/report.json`). `python
scripts/check_results.py` fails if any number here does not equal a cited field.

These are **case studies, not accuracy rates** ([EVAL, Principles](EVAL.md)). company_a and company_b are
**development goldens**: their labels were used while building, so they show the pipeline doing
what it was built to do on them, not how it generalises. The held-out report has not been scored
yet (below).

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

Human rating (the tech lead, one rater, each displayed paragraph against its cited quotes):

| Rated | Supported | Unsupported | Contradicted | Cited |
|---|---|---|---|---|
| 29 | 27 | 2 | 0 | `company_a-20261003T011619Z-01552f5`: ratings.total, ratings.supported_count, ratings.unsupported_count, ratings.contradicted |

Both unsupported items are executive-summary bullets (`executive_summary:1` and
`executive_summary:3`) whose sentences claim more than the quotes they cite.

## Held-out report (company_c)

**Not yet run.** The held-out report has not been provided in `fixtures/holdout/`. When it is,
the tech lead labels it, `make eval COMPANY=company_c` is run once, and its run id and results are
recorded here, including every miss. If anything is tuned on it afterwards, this section will say
that it has become a development golden.

## What these results do not show

- How the pipeline does on reports it was not built against: that is what the held-out run is for.
- Agreement between two independent table engines: only one engine family ran.
- Commentary quality beyond one company, one model and one rater.
- Anything about NHS trusts, insurers or scanned PDFs, which are not supported.
