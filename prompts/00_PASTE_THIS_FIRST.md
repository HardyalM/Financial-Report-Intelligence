# PASTE THIS FIRST

New Claude Code session. Repo has `CLAUDE.md`. No app code yet.

---

You are a principal engineer on an unlimited-tooling budget. I am the tech lead.

We are building **Financial Report Intelligence & RAG**: upload a UK annual report PDF → extract statements → calculate ratios in code → grounded executive commentary with page citations → analyst dashboard.

I do **not** want you to build it in this session.

I want the best possible implementation plan, written into `docs/`.

Read and obey `CLAUDE.md` and `prompts/01_PLANNING_PROMPT.md` if present. If that file is in this repo, treat it as the full brief. If not, follow the instructions below.

## Standing law

- Numbers are a typed `StatementPack`. Ratios are Python.
- The LLM never computes ratios and never invents a missing line item.
- v1 excellence on 2–3 labelled PDFs beats fake generality.
- Planning only. Zero application code. Zero “let me scaffold quickly.”

## High-budget posture

Choose the strongest credible stack, not the cheapest:

- dual-engine PDF parsing with reconciliation (premium document intelligence + local digital parser)
- optional vision pass on *statement pages only* as a third vote
- Postgres + pgvector
- best available embedding + reranker
- frontier model for mapping assistance; fast model for commentary
- Next.js + Tailwind + shadcn
- tracing (Langfuse or equivalent)
- object storage for source PDFs

If a vendor is optional, say so. Always include a fallback so the repo still runs locally.

## Write these files

- `docs/PLAN.md`
- `docs/ARCHITECTURE.md`
- `docs/SCHEMA.md`
- `docs/EXTRACTION.md`
- `docs/RAG.md`
- `docs/EVAL.md`
- `docs/RISKS.md`
- `docs/COST_AND_OPS.md`
- `docs/MILESTONES.md`
- `docs/OPEN_QUESTIONS.md`

Inspect `schemas/` and `fixtures/` first. If golden PDFs or expected JSON are missing, plan anyway and specify exactly what I must label before M2.

End with:

```
PLAN COMPLETE
I will not implement until you approve.
```
