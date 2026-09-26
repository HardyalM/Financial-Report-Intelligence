# How to run this in Claude Code

You are the tech lead. Claude Code is a very expensive senior engineer who will invent finance if you let it.

## Before session 1

1. Create an empty git repo.
2. Copy `CLAUDE.md` to the **repo root**.
3. Copy `schemas/` and `fixtures/` into the repo.
4. Put 2–3 real annual report PDFs in `fixtures/pdfs/`.
5. Fill in at least **one** `fixtures/expected/*.json` by hand from the PDF. Ten to twenty line items is enough to start.
6. Add API keys later. Planning does not need them.

Recommended first PDFs (digitally born, not scans):

- one FTSE 100 non-financial
- one UK high-street bank
- optional NHS Trust annual report

## Session protocol

Every session:

```
1. Paste the prompt for that session only.
2. Tell Claude: "Follow CLAUDE.md. Do not skip ahead."
3. When it finishes, you open the PDF and check numbers yourself.
4. Commit. Then start the next milestone in a fresh conversation if context is fat.
```

Do **not** paste all milestone prompts at once.

## Model posture (ultra high budget)

- Planning, architecture, extraction design, eval design: strongest reasoning model available.
- Implementation of boilerplate: fast model is fine.
- Hard table pages / mapping disputes: strongest model + the actual page dump.
- Runtime commentary in the product: cheaper low-latency model is fine **after** retrieval.

Never use the coding agent as the production extractor of financials from a 150-page paste.

## Stop conditions

Stop the agent and take over if it:

- calculates a ratio from prose
- “fills in” a missing line item
- changes a ratio definition to make a test pass
- says parsing is “good enough” without matching `expected.json`
- builds UI before M3 tests are green
