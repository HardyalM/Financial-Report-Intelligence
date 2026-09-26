# COST AND OPS — per-report cost, latency budget, observability

Budget is not the constraint, but it still has to be known. Every price below is **as researched in September 2026** and must be re-checked before relying on it (sources in §5). All figures are in US dollars, because vendors bill in dollars.

---

## 1. Per-report cost at premium settings

### Assumptions (a typical FTSE 100 annual report)

- 200 PDF pages.
- About 150,000 tokens of indexable narrative after exclusions.
- 4–8 statement pages; the vision vote runs on up to 6.
- Mapping assistance: up to 4 LLM calls of about 4k input and 1k output tokens.
- Vision: about 2,500 image tokens plus 1,500 prompt tokens per page; about 1,200 output tokens per page.
- Rerank: 4 topics × 4 queries × 40 candidates × about 450 tokens = about 288k tokens.
- Commentary: 4 topic calls plus 1 summary call, about 30k input and 4.5k output tokens in total, including one retry's worth of budget.

### Default premium configuration

| Component | Choice | Unit price | Cost per report |
|---|---|---|---|
| Premium parse (whole document) | Azure DI `prebuilt-layout` | $10 per 1,000 pages | **$2.00** |
| Local parse | PyMuPDF + pdfplumber | — | $0.00 (compute only) |
| Vision third vote | Claude Opus 5.5, 6 pages (24k in / 7.2k out) | $4 / $20 per million tokens | $0.24 |
| Mapping assistance | Claude Opus 5.5, number-blind (16k in / 4k out) | $4 / $20 per million tokens | $0.14 |
| Embeddings | `voyage-4-large`, about 150k tokens | $0.12 per million tokens | $0.02 |
| Rerank | `rerank-3`, about 288k tokens | $0.05 per million tokens | $0.01 |
| Commentary | Claude Sonnet 5 (30k in / 4.5k out) | $2 / $10 per million tokens | $0.11 |
| **Total** | | | **≈ $2.52** |

Premium parsing is about **80 %** of the variable cost. Everything LLM-related together costs about $0.50.

### Other configurations

| Configuration | What changes | Cost per report |
|---|---|---|
| **Maximum** (v1.1: needs the Reducto adapter; frontier commentary) | Adds Reducto r-1 as a second premium engine ($10 per 1,000 pages, +$2.00); commentary on Opus 5.5 (+$0.11) | **≈ $4.63** |
| **LlamaParse variant** (v1.1 adapter) | Agentic tier instead of Azure: 10 credits/page at $1.25 per 1,000 credits = $2.50; Agentic Plus (45 credits/page) = $11.25 | $3.02 / $11.77 |
| **Lean** (still dual-engine) | Azure DI on the ~8 statement pages only ($0.08); no vision; commentary on Haiku 4.5 ($1 / $5 per million tokens) | **≈ $0.31** |
| **Local fallback** | No vendor keys | **$0.00** plus local compute |

The **lean** configuration shows that the premium spend is a choice, not a requirement: extraction accuracy on the goldens should be identical. Narrative chunking quality (Azure's reading order and paragraph roles) and tie-break coverage are what the premium spend buys. [OQ-7](OPEN_QUESTIONS.md) decides the default.

### Development costs

| Item | Estimate | Note |
|---|---|---|
| Premium parses of the fixtures | About $6–12 in total | 3 PDFs × 1–2 engines × $2, **once**, because stage artefacts are cached by `(sha256, stage_version)` |
| Live eval runs | About $0.50 each | Parsing is cached, so only the LLM, embedding and rerank calls repeat |
| Embeddings and rerank in development | About $0 | Voyage's free token allowance covers development volumes |
| **Claude Code sessions** | **The largest and least predictable cost** | Set a hard spend cap on the account before M0. Fresh sessions per milestone keep the context, and so the cost, down. |

### Fixed monthly costs (hosted demo: v1.1, not v1)

- Supabase (Postgres, pgvector, Storage), Langfuse Cloud, Vercel (frontend) and a scale-to-zero container host (for example Cloud Run) all have free tiers that are enough for a portfolio demo.
- Note that free-tier databases may pause when idle.
- Moving to paid tiers would cost in the low tens of pounds a month; check current pricing first.

---

## 2. Latency budget (200-page report)

| Stage | p50 target | p95 ceiling | Notes |
|---|---|---|---|
| Upload, hash, store | 2 s | 5 s | |
| Text layer (PyMuPDF) | 3 s | 8 s | |
| Locate statements | < 1 s | 2 s | |
| Local tables (pdfplumber, statement pages only) | 5 s | 15 s | pdfplumber is slow; never run on all pages |
| Premium parse (Azure DI, whole document, asynchronous) | 60 s | 180 s | Runs **in parallel** with the local stages |
| Vision vote (6 pages, parallel) | 20 s | 45 s | Optional |
| Mapping (deterministic + LLM leftovers) | 10 s | 30 s | |
| Reconcile, checks, pack | < 2 s | 5 s | |
| Ratios | < 0.1 s | 0.5 s | |
| Chunk and embed | 10 s | 30 s | Batched |
| Retrieve and rerank (4 topics, parallel) | 2 s | 5 s | |
| Commentary (4 topics parallel, then summary) | 25 s | 60 s | +20 s if a retry fires |
| **Pack and ratios available** | **≈ 1.5 min** | **≈ 3.5 min** | Premium parse dominates |
| **Commentary available** | **≈ 2.5 min** | **≈ 5 min** | |
| Dashboard read after processing | < 300 ms | 800 ms | Precomputed JSON |

The UI streams stage progress from the `jobs` table, so the analyst is never staring at a spinner with no information.

---

## 3. Observability

### Tracing (Langfuse)

- One **trace per document run**, with a span per pipeline stage.
- Every LLM, embedding and rerank call is a generation span recording:
  - provider and model id
  - `prompt_version`
  - input and output tokens
  - cost
  - latency
  - cache hit or miss.
- The commentary record stores its `trace_id`, so any paragraph can be traced back to the exact prompt and evidence.
- **Fallback:** JSONL traces under `artifacts/traces/`.

### Structured logs (structlog, JSON)

- **Fields:** `run_id`, `document_sha256` (prefix), `stage`, `engine`, `duration_ms`, counts (pages, tables, candidates, warnings by code, validator rejections by code).
- **Never logged:** report text, quotes or prompt bodies (rule from `CLAUDE.md`). Content lives only in the database, in artefacts, and in Langfuse (which has masking enabled for private uploads).

### Metrics to watch (from logs and eval reports)

- Stage durations (p50/p95) and premium-parse cost per document.
- **Null rate** per canonical item and **engine agreement rate**: a rising disagreement rate means a layout the rules don't cover.
- Validator rejection counts by code: a rising naked-number rate means prompt or model drift.
- Share of reports blocked on `unit_ambiguous` or `currency_ambiguous`.

### Health and resilience

- `GET /healthz` (process) and `GET /readyz` (database, storage, configured vendors).
- **Jobs:** idempotent stages; up to 3 attempts with exponential backoff.
- **Per-vendor timeouts:** Azure DI polling 300 s, LLM 60 s, embeddings 30 s, rerank 15 s.
- **Vendor failure (v1):** when a vendor call fails after its retries, that run uses the fallback path and records `source.parser_engines` or `retrieval_degraded`, and the UI shows the reduced-verification banner. A cross-run circuit breaker is **v1.1** (removed from v1 at review as hidden scope).

---

## 4. Security and data handling

- **Secrets:** in environment variables or a secret manager only; `.env.example` lists names, never values.
- **Uploads:**
  - maximum 50 MB
  - PDF magic-byte check
  - encrypted files rejected
  - PDF JavaScript and embedded files are never executed or extracted.
- **Hosted demo (v1.1):**
  - public access to precomputed goldens only
  - uploads behind a shared password with a **daily cap** (for example 10 per day), because premium parsing spends real money
  - originals deleted after 30 days.
- **Data residency:** v1 runs locally; the v1.1 hosted target is Supabase London. Azure DI in UK South. LLM, embedding and rerank vendors may process data outside the UK. This is acceptable for **public** annual reports; for private management accounts it needs vendor agreements (production note, ADR-004).
- **Evidence is untrusted input:** it is wrapped as data in prompts, and the validators do not rely on the model obeying instructions.

---

## 5. Price sources (checked September 2026)

| Price | Source |
|---|---|
| Azure DI Layout $10 per 1,000 pages; Read $1.50 per 1,000; add-ons $6 per 1,000 | [DocuOCR summary of Azure pricing](https://docuocr.com/blog/azure-document-intelligence-pricing). Microsoft's own page renders prices client-side; confirm in the [Azure pricing page](https://azure.microsoft.com/en-us/pricing/details/ai-document-intelligence/) or pricing calculator. |
| Reducto Parse r-1 $10 per 1,000 pages (legacy $15–30, 2× for agentic) | [Reducto docs: usage and pricing](https://docs.reducto.ai/reference/credit-usage) |
| LlamaParse tiers (1 / 3 / 10 / 45 credits per page), $1.25 per 1,000 credits | [LlamaParse pricing docs](https://developers.llamaindex.ai/llamaparse/general/pricing/) |
| Voyage `voyage-4-large` $0.12/M, `voyage-finance-2` $0.12/M, `rerank-3` $0.05/M; 1024-dimension defaults | [Voyage pricing](https://docs.voyageai.com/docs/pricing); [Voyage models (MongoDB docs)](https://www.mongodb.com/docs/voyageai/models/) |
| Claude Opus 5.5 $4/$20, Sonnet 5 $2/$10, Haiku 4.5 $1/$5 per million tokens | [BenchLM price tracker](https://benchlm.ai/anthropic/api-pricing), a **third-party** source. Confirm on Anthropic's pricing page before relying on it. |
