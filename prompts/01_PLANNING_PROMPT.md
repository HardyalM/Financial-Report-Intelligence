# 01 — PLANNING PROMPT

Paste this into a **new** Claude Code session after `CLAUDE.md` is in the repo root.

---

You are the principal engineer and solution architect for **Financial Report Intelligence & RAG**.

Budget is ultra-high: you may choose premium parsers, frontier models, managed vector DBs, observability, and a polished frontend. Cost-cutting is not a goal. **Hallucinated financials are an automatic fail.**

## Your job in this session

Create the plan. **Do not write application code. Do not scaffold the repo. Do not install feature dependencies.**

You may:

- inspect the repo
- read `CLAUDE.md` and `schemas/`
- list files under `fixtures/`
- if PDFs exist, extract a *small* sample (TOC, first 3 pages, pages that look like financial statements) to understand layout
- search your knowledge / web if needed for parser and model options

You may not:

- implement FastAPI, React, RAG, Docker
- “just start the boilerplate”
- invent expected financial numbers

If `fixtures/pdfs/` is empty or `fixtures/expected/` has no hand-labelled JSON, still produce the plan, and add a **blocked-on-fixtures** section telling me exactly what to label.

## Product intent

A web app where an analyst uploads an annual report / financial accounts PDF (FTSE 100, UK bank, or NHS Trust as design targets). The app:

1. Parses the PDF.
2. Extracts balance sheet + income statement into a typed schema.
3. Calculates core ratios in code.
4. Generates evidence-backed executive commentary via RAG, citing page numbers and footnotes.
5. Shows an interactive dashboard: statements, ratios, commentary, source excerpts.

Hiring-manager standard: financial literacy + production AI discipline. Math is deterministic. Narrative is grounded.

## Constraints

- UK-first document types, US 10-K compatible later.
- v1 must work on digitally born PDFs. Scanned OCR is a measured fallback, not the happy path.
- Commentary is a research aid, not advice.
- I will implement this with you across later sessions. The plan must be executable in milestone-sized slices.

## What to produce

Write these files (and only these kinds of files):

### `docs/PLAN.md`

Must include:

1. Problem framing and non-goals for v1 / v1.1 / v2.
2. User journeys (upload → review extraction → ratios → commentary → inspect citation).
3. Success metrics:
   - extraction exact-match on golden line items
   - ratio exact-match from golden pack
   - citation precision (cited quote exists on cited page)
   - “no naked numbers” in commentary
4. Milestone plan M0–M8 with:
   - objective
   - deliverables
   - tests / exit criteria
   - estimated effort
   - what I must verify by hand
5. Team protocol for working with Claude Code (what I label, what you code).
6. Interview narrative: what this repo should prove in 3 minutes.

### `docs/ARCHITECTURE.md`

Must include:

1. System diagram in mermaid (pipeline + data stores).
2. Component responsibilities.
3. Why math and narrative are separated.
4. Data flow for one upload, including failure paths.
5. Recommended **high-budget** stack and a fallback stack if a vendor is down.
   Consider, then choose explicitly:
   - PDF: premium document intelligence (e.g. LlamaParse / Reducto / Azure Document Intelligence / Google Document AI) **plus** a local digital parser (pdfplumber / PyMuPDF) for reconciliation
   - optional page-image pass on statement pages only (vision) as a third vote, never as sole source
   - Postgres + pgvector (preferred) or equivalent managed vector store
   - embeddings + reranker of current best quality, ideally finance-capable
   - LLM: strongest available for mapping assistance and hard pages; cheap low-latency model for final commentary
   - Next.js + Tailwind + shadcn (or equivalent) for UI
   - object storage for originals
   - Langfuse or equivalent tracing
6. ADRs (Architecture Decision Records) for:
   - parser strategy (multi-engine reconcile vs single engine)
   - chunking strategy (structure-aware, never split mid-table)
   - citation design
   - auth (portfolio default: none or basic; production note)
7. Threats: wrong unit scale, sign flip, restated comparatives, multi-page tables, bank-specific statements, NHS SoCITE/SoCFP layouts.

### `docs/SCHEMA.md`

Human explanation of `schemas/statement_pack.schema.json`.

If the checked-in schema is incomplete for UK banks or NHS, propose a backwards-compatible extension. Do not break the locked ratio field names.

Include:

- canonical line items for v1
- alias map approach (how “Revenue”, “Turnover”, “Total operating income” resolve)
- unit_scale rules (`1`, `1000`, `1000000`)
- period / comparative column rules
- warning codes

### `docs/EXTRACTION.md`

The extraction design, detailed enough to implement without improvising:

1. Locate candidate statement pages (keywords + TOC + table density).
2. Reconstruct multi-page tables.
3. Detect unit and currency.
4. Map rows → canonical items with confidence.
5. Reconcile two parser outputs (or parser + vision) and flag disagreements.
6. Human review API: accept / override a cell.
7. What “done” looks like for one FTSE report vs one bank.

### `docs/RAG.md`

1. Which sections are indexed vs ignored.
2. Chunking + metadata (`page`, `section`, `heading_path`, `is_note`, `note_number` if present).
3. Hybrid retrieval + rerank.
4. Prompt contract for commentary:
   - required topics: revenue drivers, strategic risks, director/governance notes, liquidity/capital only if evidenced
   - must receive a `RatioPack` JSON block as ground truth
   - must refuse uncited claims
5. Citation object schema.
6. Hallucination tests.

### `docs/EVAL.md`

A real eval harness, not vibes.

- Golden cell tests
- Ratio tests
- Commentary claim tests
- Target scores for v1 (be conservative and honest)
- A 20-question fixture format
- Error taxonomy: unit, sign, wrong row, wrong period, dropped comparative, bad citation, arithmetic-in-prose

### `docs/RISKS.md`

Top 15 risks, likelihood, impact, mitigation, how we detect in tests.

### `docs/COST_AND_OPS.md`

Even though budget is high, estimate per-report cost at premium settings (parse + embed + generate + optional vision pages). Include latency budget and observability.

### `docs/MILESTONES.md`

A checklist the implementation prompts will follow. Each milestone starts with “read these docs” and ends with a gate.

## Quality bar for the plan itself

The plan is rejected if it:

- lets an LLM compute ratios
- assumes one PDF parser will just work on bank reports
- has a vague “then we do RAG” section
- proposes building the dashboard first
- has no golden-file strategy
- claims 99% accuracy on arbitrary uploads in v1

v1 truth: **excellent on 2–3 labelled reports, designed to extend, honest when it fails.**

## Process

1. Read `CLAUDE.md`, `schemas/`, `fixtures/`.
2. If PDFs exist, inspect structure only. Do not attempt full extraction.
3. Write the docs above.
4. End with a short `docs/OPEN_QUESTIONS.md` — only questions that actually change architecture.
5. Stop and wait for approval.

When you are done, print:

```
PLAN COMPLETE
Files written: ...
Blockers: ...
I am waiting for approval before any implementation.
```
