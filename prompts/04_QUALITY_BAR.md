# 04 — Quality bar and definition of done

## v1 is done when all of these are true

- At least 2 real PDFs in fixtures.
- At least 1 PDF has hand-labelled expected statements **and** ratios.
- Extraction matches labelled cells exactly (or documented rounding).
- Ratios match the locked formulas.
- Commentary on the golden report has working page citations.
- Dashboard shows warnings when a field is missing instead of hiding them.
- README explains architecture in one diagram and says what fails.
- A stranger can run locally with a `.env.example`.

## What “ultra high budget” is allowed to buy

Yes:

- best document parser APIs
- vision pass on statement pages as a **vote**
- Voyage / premium embeddings + reranker
- frontier model for mapping assistance
- Langfuse traces
- polished UI
- Playwright
- managed Postgres

No:

- skipping golden files because the model “usually gets it”
- ten agents arguing about EBITDA
- scraping Yahoo Finance to paper over a bad parse
- auto-publishing commentary as a recommendation

## Interview bar

You should be able to say, without notes:

1. Which line items feed ROCE, and why year-end not average in v1.
2. What happens if the two parsers disagree.
3. How a number is blocked from commentary if it is not in the pack or a quote.
4. One real failure you saw on a bank or NHS PDF.

If you cannot say those, the project is not ready to show.
