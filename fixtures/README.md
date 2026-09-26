# Fixtures

Claude Code is not allowed to invent these numbers.

## Layout

```
fixtures/
  pdfs/
    company_a.pdf
    company_b.pdf
  expected/
    company_a.json
    company_a.ratios.json
    company_a.retrieval.json
```

## How to label `company_a.json`

Open the PDF. Find the consolidated income statement and statement of financial position.

Copy the printed figures **as printed**, then set `unit_scale` to match the header (`£ million` → 1000000).

Keep v1 items only:

- revenue
- operating_profit
- current_assets
- current_liabilities
- total_equity
- total_debt

Add others if obvious. Leave null if not obvious.

## `company_a.ratios.json`

Compute with a calculator from your labelled cells using the locked formulas in `CLAUDE.md`.  
Do this before you trust the pipeline.

## `company_a.retrieval.json`

Five queries is enough:

```json
{
  "queries": [
    {
      "q": "What are the principal risks?",
      "must_include_page_any_of": [12, 13, 14]
    }
  ]
}
```
