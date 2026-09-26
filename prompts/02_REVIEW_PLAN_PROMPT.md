# 02 — REVIEW AND HARDEN THE PLAN

Run this in the same repo after `docs/PLAN.md` exists. Still no application code.

---

Review every file under `docs/` against `CLAUDE.md`.

You are a hostile principal engineer + a credit analyst.

## Attack the plan

Find and fix:

1. Any path where a model-generated number can reach a ratio or the dashboard without a `StatementPack` field.
2. Any milestone that is too large to finish in one focused session.
3. Missing failure UX (what the analyst sees when revenue is unmapped).
4. Bank and NHS layouts treated as “same as a corporate P&L.”
5. Chunking that splits tables or loses note numbers.
6. Eval that only checks the LLM “sounds good.”
7. Hidden scope: comps, valuation, agents, multi-tenant SaaS, live prices.
8. Ratio definitions that drifted from `CLAUDE.md`.

## Improve

- Tighten `docs/MILESTONES.md` exit criteria until they are binary.
- Add a `docs/ADR/` folder only if an ADR is still buried in prose.
- Add `docs/UI.md`: one primary screen, component list, what is *not* on v1.
- Add `docs/INTERVIEW.md`: 90-second walkthrough, likely questions, answers that cite our architecture.

## Still forbidden

Application code, dependency installation for the app, dummy dashboards.

End with a diff-style summary of what you changed and whether the plan is approved internally by you. I will still give the human go / no-go.
