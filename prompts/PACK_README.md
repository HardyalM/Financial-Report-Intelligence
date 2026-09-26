# Claude Code Pack — Financial Report Intelligence & RAG

Use this pack to make Claude Code **plan first**, then build.

This is not a “one prompt builds the product” kit.  
It is a **high-budget, interview-grade** build process:

1. Claude writes the plan, architecture, schema, evals, and risks.
2. You approve the plan.
3. Claude implements **one milestone at a time**, against golden PDFs and tests.
4. Numbers never come from an LLM. Commentary does, with citations.

## Files

| File | Purpose |
|---|---|
| `00_HOW_TO_USE.md` | Exact operating procedure in Claude Code |
| `CLAUDE.md` | Standing constitution. Keep this in the repo root. |
| `prompts/01_PLANNING_PROMPT.md` | **Run this first.** No application code. |
| `prompts/02_REVIEW_PLAN_PROMPT.md` | After the plan exists. Tightens it. |
| `prompts/03_MILESTONE_PROMPTS.md` | Copy-paste prompts for M0–M8 |
| `prompts/04_QUALITY_BAR.md` | Definition of done, evals, interview narrative |
| `schemas/statement_pack.schema.json` | Locked numeric contract |
| `fixtures/README.md` | How to add golden PDFs + expected JSON |

## Rule

If Claude starts writing FastAPI routes or React pages during planning, stop it.
