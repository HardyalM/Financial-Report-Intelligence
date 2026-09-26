# UI — one primary screen

v1 has **one primary screen: the Report screen**.
- Upload is its empty state.
- Evidence, provenance and review happen in a panel on the same screen.
- The only other page is a static **Limitations** page (M8.3), linked from the footer.

---

## 1. Principles

1. **Evidence is one click away.** Every figure, ratio input and citation opens its source page with the exact text highlighted.
2. **Nulls are visible and explained.** A missing figure is never hidden, never shown as zero, and never "estimated". It says what is missing, why, where we looked and what you can do.
3. **Suggestions look like suggestions.** Anything a model proposed is labelled "Suggested by model" until a person confirms it.
4. **Manual is marked for good.** A figure a person entered or forced, or a unit a person confirmed, carries a permanent badge, and every ratio that uses it inherits the badge.
5. **Numbers are formatted by code, not written by a model:** £13.9bn, £907.5m, 6.3 %, 1.54x, +0.4 pp.
6. **Research aid, not advice.** No buy, sell or hold language anywhere, and the footer says so on every view.

---

## 2. Layout (desktop, width ≥ 1280 px)

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ A  Company plc · Annual Report 2025 · Consolidated · [Corporate] · [£m GBP] · [Ready]     │
│    badges: [Unit confirmed manually] [Reduced verification]                (if present)   │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ B  Banner stack (highest priority first, §8)                                             │
├─────────────────────────────────────────────────────┬─────────────────────────────────────┤
│ C1 Numbers snapshot (code-rendered, one line)        │ D  Evidence panel (sticky)          │
│                                                      │   D1 PDF page viewer + highlight    │
│ C2 Key figures                FY2025   FY2024  Δ     │   D2 Provenance card                │
│    Revenue                    12,345.0 11,890.0 …    │   D3 Review actions (when relevant) │
│    [p.142] [Note 3] Two engine families agree        │                                     │
│    Operating profit           — Needs review (2)     │   Empty: "Select a figure, ratio    │
│    …                                                 │   input or citation to see its      │
│                                                      │   source."                          │
│ C3 Ratios  [Op. margin] [Current] [D/E] [ROCE]       │                                     │
│                                                      │                                     │
│ C4 Commentary                                        │                                     │
│    Executive summary · Income drivers · Risks ·      │                                     │
│    Governance · Liquidity & capital (if evidenced)   │                                     │
├─────────────────────────────────────────────────────┴─────────────────────────────────────┤
│ Footer: Research aid. Not investment advice. · Limitations · Model and prompt versions     │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Narrower than 1280 px:** the evidence panel becomes a bottom sheet.
- **Below 768 px:** the screen is read-only; review actions are desktop-only in v1.
- The figures in the sketch are the fictional `EXAMPLE` numbers.

---

## 3. Empty and processing states

| State | What the main column shows |
|---|---|
| **Empty** | Upload dropzone: "Drop an annual report PDF (up to 50 MB). Digitally born PDFs work best." Links to the precomputed golden reports. |
| **Processing** | Stage stepper, driven by the `jobs` table: Reading pages → Finding statements → Extracting figures → Checking → Calculating ratios → Indexing narrative → Writing commentary. Each step shows done, running or fallback. Stages finish independently, so figures appear before commentary. |
| **Needs unit confirmation** | A blocking dialog showing the header crop (or crops) with the unit tokens found, a choice of currency and scale, and the evidence page. Nothing else is shown until it is confirmed. |
| **Needs document type** | The figures table renders; ratio cards show *withheld*; a banner offers "Corporate / Bank / NHS trust / Other" with the signals found. |
| **Failed** | The error in plain English and the stage it failed at; a retry button; the job id. |

---

## 4. Key-figure row states

Each row shows the canonical label, the printed label (on hover), both periods, the change, and chips.

| # | State | When | Display | Actions |
|---|---|---|---|---|
| R1 | **Published: verified** | Two engine families agree | Value · `[p.N]` · `[Note N]` · "Two engine families agree" | Open evidence |
| R2 | **Published: single family** | One family (for example Azure unavailable) | Value · chips · "One engine family" | Open evidence |
| R3 | **Derived** | `total_debt` | Value · "Derived: sum of 4 lines" · expander listing each component with page chips; `assumed_zero` components labelled "Not presented (section fully checked)" | Open each component |
| R4 | **Confirmed by you** | A candidate or model suggestion accepted | Value · chips · badge "Confirmed by you" | Undo (appends a new override) |
| R5 | **Manual: not found on page** | Forced, unanchored value | Value · **amber** badge "Manual: not found on page" · reason on hover | Undo |
| R6 | **Needs review** | Null, with deterministic candidates (disagreement or low confidence) | "— Needs review (2 candidates)" and the warning in words: "The two engine families read different figures on p. 142" | Opens review in D3 |
| R7 | **Suggested by model** | Null, with an LLM pointer suggestion | "— Suggested by model: confirm?" · the suggested row label (never a number until confirmed) | Opens review in D3 (confirm or reject) |
| R8 | **Not found** | Null, no candidates | "— Not found" and **where we looked**: "Searched the consolidated income statement (pp. 142–143) for: revenue, turnover, group revenue" | "Enter from a page" (anchored) · "Point to the statement page" |
| R9 | **Not applicable** | Null by design (for example a bank's current assets) | "Not applicable: the balance sheet has no current/non-current split" | None |
| R10 | **Blocked** | Unit or currency unconfirmed | The whole table is greyed with "Confirm the unit to see figures" | Opens the unit dialog |

Warning codes are always translated into a sentence. The code itself is shown only on hover, for traceability.

---

## 5. Ratio-card states

Each card shows the **name**, both periods, the change (in pp for margins and ROCE; absolute for multiples), the **locked formula** as text (for example "Operating profit ÷ Revenue"), and each input with its value and page chip.

| # | State | Display |
|---|---|---|
| K1 | **OK** | Values and change. Inputs listed with page chips. Help text: "Year-end balances; seasonal businesses may differ within the year." |
| K2 | **OK with flag** | The value is **shown**, with "Not meaningful: negative equity" beside it (ADR-008). It is never hidden. |
| K3 | **Missing input** | "—" and "Needs current liabilities: not found", as a link that scrolls to and highlights row R6, R7 or R8 |
| K4 | **Not applicable** | "Not applicable to banks" (or the relevant explanation) and a one-line reason |
| K5 | **Withheld** | "Document type unclear: confirm to show ratios", with a button that opens the choice |
| K6 | **Uses a manual input** | The K1 or K2 display plus the inherited badge "Uses a manual figure" |

**D/E card only:** an expander splits `total_debt` into borrowings and lease liabilities. For retailers, IFRS 16 leases can dominate debt, and a credit reader needs to see that split.

---

## 6. Evidence panel

### 6.1 PDF viewer

- pdf.js rendering of the original PDF, with the page index and the printed folio ("PDF p. 142 · printed p. 140").
- Highlight boxes come from text-layer bounding boxes: the cell for a figure, the lines for a quote (one box per page when a quote crosses pages).
- Zoom; previous and next page.

### 6.2 Provenance card

| For a figure | For a citation |
|---|---|
| Printed label; `raw_text` as printed; page and folio; note reference; unit | Section path (for example Strategic report › Principal risks › Supply chain) |
| Engine families that agreed; checks passed or failed (for example "Current assets = sum of 6 rows ✓") | Note number (if any); match type (exact or normalised) |
| Verification label; all warnings in words | The full quote |

### 6.3 Review actions (shown only when the selected item needs a decision)

- **Candidates:** each shows a page crop, the engine family and the reason it is in dispute, with a "Use this" button.
- **Model suggestion:** the suggested row highlighted on the page, with "Confirm" and "Reject" buttons.
- **Enter from a page:** the reviewer enters the page number, then selects the printed text on the page (or types it).
  - The server checks that it is on the page.
  - If it is not, the panel says: *"That text isn't on page N. Check the page number or select the figure on the page."* Forcing it needs a reason and produces an R5 row.
- **Set to null:** requires a reason.
- **Point to the statement page:** a page picker, which re-runs extraction for that statement.

---

## 7. Commentary

- **Executive summary:** 3–5 bullets, each with numbered citation markers.
- **Numbers snapshot:** one code-rendered line. Nulls appear as "not available (reason)".
- **Topic panels:** Income drivers · Strategic risks · Governance and directors' notes · Liquidity and capital (only if evidenced).
- **Placeholders** render with a subtle underline. Clicking one selects the source figure or ratio.
- **Quoted figures** render in quotation marks, with their citation. They come from the company's text, not the packs, and never feed a ratio.

| Topic state | Display |
|---|---|
| `ok` | Paragraphs with citation markers |
| `insufficient_evidence` | "There isn't enough in the report to comment on this topic." |
| `validation_failed` | "Commentary withheld: it failed evidence checks (N paragraphs removed)." Reasons on hover. |
| Not evidenced (liquidity only) | A collapsed line: "No liquidity or capital evidence retrieved." |
| Extractive mode | Label "Extractive summary: no generated text", followed by verbatim passages with citations |
| Stale | Banner: "Figures changed since this commentary was written", with a **Regenerate** button |

---

## 8. Banner stack (priority order)

1. Unit or currency needs confirmation (blocking).
2. Document type unclear (ratios withheld).
3. Statement not found: names the statement, lists the pages scanned and rejected candidates, and offers "Point to the page".
4. Reduced verification: only one engine family ran.
5. Not digitally born: figures are review suggestions only.
6. Commentary stale.
7. A stage fell back (for example "Retrieval used lexical search only").

Banners explain, then offer the one action that resolves them. Each can be dismissed for the session but reappears on reload if still true.

---

## 9. Components

| shadcn/ui | Custom |
|---|---|
| Card, Table, Badge, Button, Alert, Dialog, Sheet, Tooltip, Input, Select, Separator, ScrollArea, Skeleton | `ReportHeader`, `BannerStack`, `UploadDropzone`, `ProgressStepper`, `FiguresTable`, `FigureRow` (R1–R10), `PageChip`, `NoteChip`, `VerificationLabel`, `RatioCard` (K1–K6), `CommentaryPanel`, `CitationMarker`, `EvidencePanel`, `PdfViewer`, `ProvenanceCard`, `ReviewPanel`, `UnitDialog` |

Every state has a `data-testid` (for example `figure-row-state-R8` or `ratio-card-state-K4`), so the M7.x Playwright gates can check one test per state.

---

## 10. Copy and accessibility

- **UK English throughout** ("analyse", "organisation", "per cent" in prose; "%" in figures).
- **No** "AI thinks", "insights", "recommend", "buy", "sell", "undervalued" or "attractive". Use neutral verbs: *reports*, *states*, *identifies*.
- **Status never relies on colour alone:** every badge has an icon and text; amber and highlight colours meet WCAG AA contrast.
- **Keyboard:** every chip and citation is focusable; Enter opens evidence; Esc closes the sheet.
- Progress updates are announced (`aria-live="polite"`).

---

## 11. Not in v1

- Charts or a charting library (both periods are shown as numbers with the change).
- Stock prices, market data, valuation, peer comparison.
- Chat or free-form questions.
- Export to Excel or PDF (v1.1).
- More than one report per company (multi-year series, v1.1).
- Accounts, sign-in, sharing, multi-tenant anything.
- Editing on mobile.
- Notifications or email.
