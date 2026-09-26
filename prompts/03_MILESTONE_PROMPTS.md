# 03 — IMPLEMENTATION PROMPTS (M0–M8)

Use **one prompt per session**.  
Replace `{company}` with the first labelled fixture.

Do not paste M4 if M3 tests are red.

---

## M0 — Repo contract

Follow `CLAUDE.md` and `docs/MILESTONES.md`.

Implement **only** the repository skeleton agreed in the plan:

- package layout
- pyproject / lint / pytest
- env example
- empty modules with type stubs matching `docs/ARCHITECTURE.md`
- CI that runs unit tests
- copy or generate types from `schemas/statement_pack.schema.json`

Do not implement parsing logic, RAG, or UI.

Exit: `pytest` collects and passes a smoke test that loads the schema.

---

## M1 — PDF inspection toolkit

Follow `CLAUDE.md`. Milestone M1 only.

Build a CLI / library that, for a PDF path, writes to `artifacts/inspect/{stem}/`:

- page count
- outline/TOC if present
- per-page: text length, table count, keyword hits (`balance sheet`, `income statement`, `statement of financial position`, `group statement of profit`, `notes to the`)
- raw table dumps from the local parser
- optional: call the premium parser **if credentials exist**, otherwise skip and record `parser_skipped`

No mapping to canonical line items yet. No ratios. No LLM required.

Add tests on a tiny synthetic PDF if you create one, plus a test that the inspector runs on `fixtures/pdfs/` without crashing.

Exit: I can open an inspect dump and find likely statement pages by eye.

---

## M2 — Statement mapping to StatementPack

Follow `CLAUDE.md`, `docs/EXTRACTION.md`, `docs/SCHEMA.md`.

Target PDF: `fixtures/pdfs/{company}.pdf`  
Target truth: `fixtures/expected/{company}.json`

Implement the mapper that produces a valid `StatementPack`.

Rules:

- Use inspect dumps + parser tables as inputs.
- An LLM may suggest row mappings. Persist the suggestion separately. Final values must come from parsed cells.
- If premium parser and local parser disagree on a golden cell, emit a warning and do not silently pick the pretty number. Prefer the engine that matches `raw_text` on the page.
- Unit scale mistakes are fatal. Add an explicit detector for “£m”, “£ million”, “£000”, “$ millions”.
- Do not implement RAG or UI.

Tests:

- schema validation
- every key in `fixtures/expected/{company}.json` matches extracted value within specified tolerance (default 0)
- page number on each golden item is correct
- a negative test: if revenue row is removed from input, result is null + warning, not a guessed revenue

Exit: golden file matches. If it does not, stop and write `docs/EXTRACTION_DEBUG_{company}.md` with the failing rows. Do not “fix” by editing expected JSON unless I told you the PDF was labelled wrong.

---

## M3 — Deterministic ratios

Follow `CLAUDE.md` locked formulas.

Implement `compute_ratios(statement_pack) -> RatioPack`.

- Pure functions, no I/O, no LLM.
- Null inputs → null ratio + reason.
- Division by zero guarded.
- Attach formula strings and input cell references.

Tests from the golden StatementPack **and** from hand-computed expected ratios in `fixtures/expected/{company}.ratios.json`. If that file does not exist, compute the expected ratios in a comment for me and wait — do not invent the expected file from untrusted extraction.

Also add property tests: scaling all inputs by 1000 must not change margin ratios; it must change nothing about current ratio / D/E / operating margin.

Exit: ratio tests green on the golden pack.

---

## M4 — Narrative index + retrieval

Follow `docs/RAG.md`.

Index only narrative sections from the same golden PDF.

- Chunk with page + heading metadata.
- Do not index raw statement tables into the vector store as if they were prose (they already live in StatementPack).
- Hybrid search + rerank as specified in the plan.
- Retriever returns `{text, page, section, score, chunk_id}`.

Tests:

- query “principal risks” returns chunks whose section/page is in the risks part of the labelled PDF (add `fixtures/expected/{company}.retrieval.json` if present; otherwise create the file format and pause for me to fill 5 queries)
- no chunk without a page number

No commentary generation yet.

---

## M5 — Grounded commentary

Follow `docs/RAG.md` and `CLAUDE.md`.

Implement `generate_commentary(statement_pack, ratio_pack, retrieved_chunks) -> Commentary`.

Prompt contract:

- System: research aid, not advice. Use only provided evidence.
- Include `RatioPack` as a JSON block labelled GROUND_TRUTH_NUMBERS.
- The model must not compute new ratios.
- Each bullet/paragraph has citations.
- If evidence is thin, say so.

Post-conditions in code (not just the prompt):

1. Strip or reject any citation whose quote is not a substring of a retrieved chunk (allow minor whitespace).
2. Flag any number in the prose that is not in StatementPack/RatioPack and not in a cited quote.
3. Persist model, retrieval set, and trace id.

Tests use canned chunks + canned packs so they run offline.

Exit: offline tests green. Then run once on the golden PDF and write the output to `artifacts/commentary/{company}.json` for my manual read.

---

## M6 — API

Implement FastAPI (or the planned backend) for:

- `POST /uploads`
- `GET /reports/{id}` (pack + ratios + warnings)
- `GET /reports/{id}/commentary`
- `GET /reports/{id}/pages/{n}` excerpt or file slice for citation preview
- `POST /reports/{id}/overrides` to correct a cell and recompute ratios

No market data. Auth as specified in the plan.

Tests: API-level, using the golden PDF or a precomputed pack to keep runtime short.

---

## M7 — Dashboard

Implement the UI in `docs/UI.md` only.

Required:

- upload
- statement tables with page chips
- ratio cards showing formula + inputs
- warning banner when fields are null
- commentary with clickable citations
- “not investment advice” footer

Forbidden:

- stock charts
- peer comps
- chat that can bypass the pack

If frontend tests were planned (Playwright), add a thin happy-path test.

---

## M8 — Second document type + honesty layer

Run the pipeline on the second fixture (bank or NHS).

- Do not break company 1 tests.
- Extend alias maps / page locators as needed.
- Add a limitations page in the UI and `README.md`.
- Fill `docs/RESULTS.md` with real scores on the two goldens, not marketing numbers.
- Write `docs/INTERVIEW.md` if it does not already exist.

Stop. This is v1.

---

## Recovery prompt (use when a milestone is a mess)

Stop implementing new features.

1. List failing tests.
2. Identify the first false number or broken contract.
3. Propose the smallest fix.
4. Implement only that fix.
5. Re-run the milestone exit tests.
6. If the PDF layout is the cause, write a page-level debug note instead of generalising the parser.

Do not refactor the whole pipeline.
