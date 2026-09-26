# CLAUDE.md — Financial Report Intelligence

You are implementing an interview-grade financial document intelligence product.

Budget is not the constraint. Correctness is.

## Product

A user uploads a company annual report / financial accounts PDF. The system:

1. Parses the PDF.
2. Extracts income statement and balance sheet into a typed schema.
3. Calculates ratios in Python from that schema only.
4. Retrieves narrative passages (strategy, risks, directors’ report, notes).
5. Generates executive commentary that cites page + quote.
6. Shows results in a clean dashboard.

## Non-negotiable architecture

```
PDF
 → parse (text + tables + page map)
 → map into StatementPack (typed JSON)
 → validate + reconcile units/signs/periods
 → pandas/numpy ratio engine
 → narrative index (page-aware chunks)
 → retrieve
 → LLM commentary (citations required)
 → UI
```

The LLM may **propose** a mapping. It may **not** be the source of truth for a number.

If mapping confidence is low: `null` + `warnings[]`. Never guess.

## Hard rules

1. Do not invent line items, units, signs, or restatements.
2. Every numeric fact in `StatementPack` must include: `value`, `unit_scale`, `currency`, `period`, `page`, `raw_text`, `confidence`.
3. Ratio code reads only `StatementPack`. No regex-over-prose fallback that silently feeds ratios.
4. Commentary numbers must be injected from `StatementPack` or copied verbatim from a retrieved quote. Model arithmetic is forbidden.
5. Every commentary claim has `{page, quote, chunk_id}`. If evidence is missing, say so.
6. Do not give investment advice. Frame output as a research aid.
7. Do not change locked ratio definitions to make outputs “look nicer.”
8. Do not build UI before statement extraction tests pass on at least one golden PDF.
9. Do not add agents, multi-company comps, or live market data unless the current milestone asks for them.
10. Prefer explicit failure over a confident wrong dashboard.

## Locked v1 ratio definitions

Document these in the UI and in code comments. Do not silently substitute.

- **Operating margin** = `operating_profit / revenue`
- **Current ratio** = `current_assets / current_liabilities`
- **Debt-to-equity** = `total_debt / total_equity`
- **ROCE** = `operating_profit / (total_equity + total_debt)`  
  Year-end balances, not averages, in v1.  
  `total_debt` = interest-bearing borrowings + lease liabilities if separately present, else borrowings only + a warning.

If a required input is null, the ratio is null with reason `missing_input`.

## Engineering standards

- Python 3.12, typed, ruff + pytest.
- One obvious module boundary per pipeline stage.
- Golden-file tests for extraction and ratios.
- Deterministic fixtures. No live network in unit tests.
- Structured logs. Never log full report text in production logs.
- Secrets only in env / secret manager.

## Planning vs implementation

If the user is in a planning session:

- Write plans and schemas only.
- Do not scaffold the app.
- Do not install a forest of dependencies “to get ready.”

If the user is in an implementation milestone:

- Implement only that milestone.
- Add tests in the same change.
- Stop and report blockers instead of widening scope.

## When you are unsure about accounting

Say you are unsure. Propose 2 options. Do not pick the option that makes the demo prettier.
