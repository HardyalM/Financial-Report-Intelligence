# INTERVIEW — how to talk about this project

This is written for you to say in your own words, not to recite.

**Anything in [square brackets] must be filled from `docs/RESULTS.md` after M8.3.** Never fill it from memory or from this plan. If a result isn't in `RESULTS.md`, don't claim it.

---

## 1. The 90-second walkthrough

> "Analysts, credit teams and finance managers spend hours pulling a handful of figures and paragraphs out of 200-page annual reports. Chat tools are quick, but they invent or rescale numbers, and in finance a confident wrong number is worse than a blank.
>
> So I split the problem in two.
>
> **Numbers** come from the primary statements only. Two independent kinds of parser read the tables: one works from the PDF's embedded text and one from the page image. Every figure has to be found in the PDF's own text layer before it counts, so no parser can 'tidy' a number. Arithmetic checks, like the balance sheet balancing and subtotals adding up, back that up. Ratios are plain Python with fixed definitions.
>
> An AI model can *suggest* which row is operating profit, but it only ever sees the labels, never the numbers, and a suggestion is never published until a person confirms it.
>
> **Narrative** — risks, revenue drivers, going concern — is retrieved from the report and summarised by a model. Every sentence has to cite a verbatim quote. Code checks the quote exists and works out the page itself. Any number in the text must either be inserted from the extracted figures or be copied inside a verified quote.
>
> When it isn't sure, it says so: a blank with a reason, not a guess. On the reports I labelled by hand it matches [N/N] figures with [0] wrong values shown. On a report I kept back for testing, it covered [X of Y], and every miss was flagged rather than wrong."

---

## 2. The three-minute demo

Follow PLAN §6. Use the precomputed golden report, so nothing depends on live APIs during the interview.

1. **Report screen.** Click a revenue page chip, and the PDF opens with the cell highlighted.
2. **A ratio card.** Point to the formula and its inputs, each with a page.
3. **A citation.** Click it, and the quote is highlighted on its page.
4. **An honest failure.** Show a null row (R6–R8): what is missing, where the tool looked, and what the reviewer can do.
5. **The bank report.** Show "Not applicable to banks" on current ratio, with the reason.

---

## 3. Questions you should be able to answer without notes

### The four from the quality bar

**Q1. Which line items feed ROCE, and why year-end rather than average?**
- ROCE = operating profit ÷ (total assets − current liabilities): the standard UK definition of capital employed, the long-term funding the business uses.
  - All inputs are printed totals on the consolidated balance sheet. If total assets isn't printed, it is derived as non-current plus current assets, and the screen shows that it was derived.
  - I chose this over "equity plus debt" because it's the textbook definition, and because it doesn't depend on assembling total debt from four separate lines.
- **Why year-end:** one annual report gives two balance sheets. An average capital figure is possible for the current year but not the prior year, so year-end keeps both years on the same basis. Averages come with multi-year series in v1.1.
- **Debt-to-equity** uses total debt (borrowings plus lease liabilities shown separately) over total equity including minority interests, so both sides cover the same group.

**Q2. What happens if the two parsers disagree?**
- Both readings must first be found in the PDF's text layer. Then the text layer, not either parser, decides which row, column and year each number belongs to.
- If they still disagree, deterministic evidence breaks the tie: the row label matches, the column is the right year, and the arithmetic checks pass.
- If that doesn't settle it, the figure is left blank with a "parsers disagree" warning and both readings go to a review queue.
- It never picks the more plausible-looking number.

**Q3. How is a number blocked from the commentary if it isn't in the extracted figures or a quote?**
- The model writes placeholders, and code fills in the numbers.
- A validator rejects any other number, in digits or in words (for example "six point three per cent", "doubled"), unless it sits inside a quote that code has verified against the source text.
- A failing paragraph is retried once, then dropped. The executive summary goes through the same checks.
- Pages are always worked out by code, never supplied by the model.

**Q4. Tell me about a real failure on a bank or NHS report.**
- [From `RESULTS.md`, for example: which line was wrong or missing, why, and the check or rule that now catches it.]
- **Do not invent this.** If M8.1 hasn't run, say the bank run hasn't been done yet.

### Finance and credit

- **Why statutory figures rather than adjusted ones?**
  - Adjusted or "underlying" figures are the company's own alternative performance measures; they vary by company and year and aren't audited on the same basis.
  - The tool takes figures only from the primary statements and explicitly excludes adjusted lines. Adjusted figures can still appear in commentary, but only as quotes.
- **Why is current ratio "not applicable" for a bank?**
  - Banks present their balance sheet in order of liquidity, not as current and non-current (IAS 1 allows this when it is more relevant). There are no current assets or current liabilities to divide.
  - The tool decides this from how the balance sheet is actually laid out, which also covers insurers, not just from the word "bank".
- **How do IFRS 16 leases affect debt-to-equity?**
  - Since 2019, most leases sit on the balance sheet as lease liabilities. For retailers they can be larger than bank borrowings, so D/E rises sharply.
  - The D/E card splits total debt into borrowings and leases, so the reader can see what's driving it.
- **Group accounts vs company accounts?**
  - UK reports include both the consolidated (group) statements and the parent company's own. The parent's balance sheet mostly holds investments in subsidiaries, so using it would give nonsense ratios.
  - The tool identifies and excludes company-only pages and columns, and a test makes sure it never picks them.
- **Negative equity?** The ratio is still shown, as the fixed formula gives it, with a "not meaningful" flag beside it. Hiding it would be changing the definition to make the output look better.
- **Restated comparatives?** The restated prior-year figure is used, because it's on the current basis, and the screen says it's restated.
- **What would you add for a credit memo?** Interest cover, net debt to EBITDA, cash conversion and a maturity profile of borrowings. That means cash flow statement and notes extraction, which is v1.1.

### AI and engineering

- **Why not just give the PDF to an AI model?** There's no way to verify its numbers, and it rescales, rounds and swaps in adjusted figures. This design makes it impossible for a model-originated number to be published, rather than just unlikely.
- **Why two kinds of parser, and why don't pdfplumber and PyMuPDF count as two?** Both read the same embedded text, so they tend to make the same mistakes. Azure's layout model works from the page image, so it fails differently. Agreement only counts across different kinds.
- **What does the AI actually do?** It makes review-only suggestions for unusual row labels (without seeing any numbers); optionally, a vision model that can only confirm a reading or flag it for review; and the narrative commentary, under strict checks.
- **How do you know it isn't hallucinating?**
  - Some things are guaranteed by construction: every displayed quote is verified; every number is traceable.
  - The rest is measured: claim-by-claim human rating against the quotes; whether it covers the report's actual principal risks and audit matters; and a test where the figures are deliberately flipped to check the commentary follows the data rather than its own assumptions.
- **How did you test it?** Hand-labelled golden reports, which must match exactly; a synthetic suite of generated statements, each testing one layout trap; a held-out report scored once; and offline tests for every way the commentary could go wrong. [Actual scores from `RESULTS.md`.]
- **Cost and speed?**
  - About $2.50 per 200-page report at premium settings (about 80 % of that is the premium parser); about $0.30 in a lean setup; zero running locally.
  - About [N] minutes to figures and [N] minutes to commentary. [Measured values from `RESULTS.md`.]
- **What if Azure is down?** It carries on with the local engines, labels the result "reduced verification", and sends more items to review. Published accuracy doesn't change; only coverage drops.
- **Prompt injection from a PDF?** Report text is treated as data, not instructions, and the checks don't depend on the model behaving.
- **What would you do next?** Cross-check figures against the company's machine-tagged ESEF/iXBRL filing; add cash flow and interest cover; add multi-year trends.

### About how you built it

- **How much of the code did you write, and can you explain it?**
  - Be accurate: "I acted as the tech lead. I wrote the plan and the accounting rules, labelled the golden reports by hand, and checked every milestone against the PDFs before accepting it. Claude Code wrote most of the implementation to that plan, one milestone at a time, with pass/fail gates."
  - Then explain one module you can walk through line by line. Pick `ratios/` or the anchoring rule, and make sure you can.

---

## 4. Things never to say

- "It's 100 % accurate", or any percentage from fewer than three documents presented as a general accuracy rate.
- "It understands the report."
- "AI-powered insights."
- "Production-ready." (It is a well-tested v1 on labelled reports.)
- "It would work on any annual report." Say instead: "It's designed to extend, and it tells you when it can't do something."
