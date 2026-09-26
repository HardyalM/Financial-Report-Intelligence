# Unilever PLC: manual labelling notes

Source: the attached `unilever-annual-report-and-accounts-2024.pdf`. All three source pages were visually reviewed. The attachment matches the reviewed copy byte for byte.

Source SHA-256: `c15d7a38b41d7baef49e78a9db9bbb1deaeec685ec160d1b7478c062eef8d6f2`.

Requested pack metadata: `schema_version: "1.1.0"`, `company_name: "Unilever PLC"`, `filename: "company_a.pdf"`, `page_count: 305`, `currency: "EUR"`, `unit_scale: 1000000`.

| Period | End date |
| --- | --- |
| FY2024 | 2024-12-31 |
| FY2023 | 2023-12-31 |

Use the 2023 comparative column in the 2024 report. The supplied 2025 report is outside this labelling scope.

| Source | PDF viewer page, starting at 1 | Printed page |
| --- | ---: | ---: |
| Consolidated income statement | 141 | 138 |
| Consolidated balance sheet | 143 | 140 |
| Note 15C | 175 | 172 |

## Transcription

The table preserves each printed amount as a raw string. The numeric `value` is the same amount with the comma removed. All amounts are EUR million. Every directly transcribed figure uses `confidence: 1.0` and `engine: "hand"`. Liabilities are positive.

| Item | Source label or location | Page | FY2024 raw amount | FY2023 raw amount |
| --- | --- | ---: | --- | --- |
| revenue | Turnover | 141 | `60,761` | `59,604` |
| operating_profit | Operating profit | 141 | `9,400` | `9,758` |
| Profit before taxation | Profit before taxation | 141 | `8,869` | `9,339` |
| Net profit | Net profit | 141 | `6,369` | `7,140` |
| current_assets | Unlabelled subtotal under Current assets | 143 | `19,194` | `17,902` |
| current_liabilities | Unlabelled subtotal under Current liabilities | 143 | `25,234` | `23,507` |
| total_assets | Total assets | 143 | `79,750` | `75,266` |
| total_equity | Total equity | 143 | `22,555` | `20,764` |
| Current financial liabilities | Financial liabilities, under Current liabilities | 143 | `6,987` | `5,087` |
| Non-current financial liabilities | Financial liabilities, under Non-current liabilities | 143 | `25,066` | `24,535` |

Current-assets and current-liabilities totals are printed subtotals. Their headings appear above the component rows. Preserve this distinction when forming `raw_text`; do not invent a printed label on the subtotal row. Total assets is printed directly and needs no derivation. Net profit includes non-controlling interests. Total equity includes non-controlling interests.

## Requested total_debt treatment

| Period | Derivation from page 143 | total_debt, EUR million |
| --- | --- | ---: |
| FY2024 | 6,987 + 25,066 | 32,053 |
| FY2023 | 5,087 + 24,535 | 29,622 |

Use `engine: "derived"` for these sums and retain evidence for both input rows. The exact derived-value object must follow the project's existing contract, which is not supplied. Do not present the calculated sum as a directly printed page-143 value.

Note 15C, viewer page 175, gives this breakdown:

| Component, EUR million | 2024 current | 2024 non-current | 2024 total | 2023 current | 2023 non-current | 2023 total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Bank loans and overdrafts | 517 | 4 | 521 | 501 | 5 | 506 |
| Bonds and other loans | 5,363 | 23,285 | 28,648 | 4,066 | 22,626 | 26,692 |
| Lease liabilities | 322 | 1,164 | 1,486 | 334 | 1,061 | 1,395 |
| Derivatives | 152 | 442 | 594 | 48 | 446 | 494 |
| Other financial liabilities | 633 | 171 | 804 | 138 | 397 | 535 |
| Total | 6,987 | 25,066 | 32,053 | 5,087 | 24,535 | 29,622 |

Leases are already included. Adding leases separately would double-count them. Derivatives contribute 594 in 2024 and 494 in 2023. Other financial liabilities include options and obligations for purchases of non-controlling interests in the US, Myanmar, India, Italy and Hong Kong; footnote (c) refers to note 21.

The requested `total_debt` is a proxy based on all financial liabilities. Preserve the full sum for this fixture, as instructed. Before M2.4, settle the code's treatment of derivatives and other financial liabilities. Removing derivatives alone would leave 31,459 and 29,128. Restricting the sum to bank loans, overdrafts, bonds, other loans and leases would give 30,655 and 28,593. Neither alternative replaces the requested fixture values here.

## Calculation worksheet

Values below are unitless ratios, rounded once to 12 decimal places from exact integer inputs using 60-digit decimal arithmetic. Multiply margin or return ratios by 100 for percentages. These calculations use the minimum requested inputs; the project's complete ratio list and JSON format are still needed.

| Calculation | Formula | FY2024 | FY2023 |
| --- | --- | ---: | ---: |
| ROCE | operating_profit / (total_assets - current_liabilities) | 0.172426443613 | 0.188527599065 |
| Operating margin | operating_profit / revenue | 0.154704497951 | 0.163713844708 |
| Current ratio | current_assets / current_liabilities | 0.760640405802 | 0.761560386268 |
| Debt to equity | requested total_debt / total_equity | 1.421103968078 | 1.426603737238 |

ROCE inputs: `9400 / (79750 - 25234) = 9400 / 54516` for FY2024; `9758 / (75266 - 23507) = 9758 / 51759` for FY2023.

## Verification and M1 status

Verified: 305 pages; source page mapping; both year columns; printed units; balance-sheet identity for both years; note 15C component sums; total-debt addition; ratio arithmetic.

The project files are absent and `finintel` is not installed in this workspace. `validate_pack` has not run. Neither JSON fixture has been created from an assumed contract. M1 is incomplete until the project example, schema/validator, derived-value format and ratio definitions are supplied, the fixtures are written, and project validation succeeds.
