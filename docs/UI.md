# UI — one primary screen

v1 has **one primary screen: the Report screen**.
- Upload is its empty state.
- Evidence, provenance and review happen in a panel on the same screen.
- The only other page is a static **Limitations** page (M8.3), linked from the footer.

*Revised 2026-10-12 (app shell): the report screen is still the primary screen. Upload's empty
state grew into a dashboard of reports (`GET /reports`, a read-only list with no figures), and
every page sits in an app shell. See section 2a.*

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

*Revised 2026-10-12 (visual redesign): an app bar, a headline-figures strip and sticky section tabs
were added. Every state, test id and rule in this document is unchanged.*

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ T  App bar (sticky): FinIntel · Reports / Company   [Research aid · not investment advice]│
│                                                     [Method & limits] [+ New report]      │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ A  ANNUAL REPORT 2025                                                                     │
│    Company plc                              [Ready] [Corporate] [£m GBP] [badges…]        │
│    Year ended … · Consolidated statements · file.pdf · N pages                            │
│ H  Headline figures (6 tiles): value · unit · change with arrow · prior year              │
│    Corporate: Revenue, Operating profit, Operating margin, ROCE, Current ratio, D/E       │
│    Bank: Total income, PBT, Cost-to-income, Loan-to-deposit, Total assets, Total equity   │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ S  Section tabs (sticky under T): Key figures · Ratios · Commentary (current one marked)   │
├─────────────────────────────────────────────────────┬─────────────────────────────────────┤
│ B  Banner stack (highest priority first, §8)         │ D  Evidence panel (sticky)          │
│ C1 Snapshot · FY2025 (code-rendered, one line)       │   D1 PDF page viewer + highlight    │
│                                                      │   D2 Provenance card                │
│ C2 STATEMENTS / Key figures   FY2025   FY2024  Δ     │   D3 Review actions (when relevant) │
│    Revenue                    12,345.0 11,890.0 ↗ …  │                                     │
│    [p.142] [Note 3] Two engine families agree        │   Empty: "Select a figure, ratio    │
│    Operating profit           — Needs review (2)     │   input or citation to see its      │
│                                                      │   source." and what it will show    │
│ C3 COMPUTED IN CODE / Ratios  [cards, K1–K6]         │                                     │
│                                                      │                                     │
│ C4 FROM THE NARRATIVE / Commentary                   │                                     │
├─────────────────────────────────────────────────────┴─────────────────────────────────────┤
│ Footer: FinIntel · Research aid. Not investment advice. · Limitations · model and versions │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Headline tiles (H)** show only values the pack or the ratio pack published, formatted by code.
  A null tile shows "—" and a short reason (Not found, Needs review, Missing input, Not
  applicable, Withheld); the full sentence stays on the row or card. A figure tile opens its row
  and source; a ratio tile scrolls to its card. A tile using a manual input carries the manual mark.
- **Change arrows** (tiles and the table's change column) are neutral: direction only, never green
  or red, because a rise is not a judgement. The arrow follows the printed, rounded figure, so a
  change shown as "0.00x" or "0.0%" has a flat arrow.
- **Narrower than 1280 px:** the evidence panel becomes a bottom sheet.
- **Below 768 px:** the screen is read-only; review actions are desktop-only in v1.
- The figures in the sketch are the fictional `EXAMPLE` numbers.

---

## 2a. App shell (2026-10-12)

- **Sidebar** (fixed; ⌘/Ctrl \ collapses it to a 60 px icon rail, remembered; a drawer below 1024 px): search, Dashboard, New report, recent reports (status dot, period; hover prefetches; right-click menu), Method & limits, and the theme switch (Light, Dark, Match system). ↑ ↓ move between rows.
- **Top bar**: breadcrumbs (Dashboard › company › status), a search field that opens the command palette, the research-aid marker, New report.
- **Command palette** (⌘/Ctrl K, anywhere): reports by fuzzy name, file or number ("Open report 12"); on a report, its sections, the original document and copy link; go to; upload; sidebar; theme. ↑ ↓ ↵, Esc clears then closes. Highlighting a report prefetches it.
- **Dashboard** (`/`, `GET /dashboard`), *revised 2026-10-12*: outcome first.
  1. **Latest result**: the newest finished report, with its headline ratios as the ratio engine stored them (and the change against the prior year), how every current-period figure was settled (read and anchored, derived in code, set by a person, left empty with the reason) and its cited passages. Open report.
  2. **Waiting for you**: each report that needs a decision, with the one action that resolves it (Confirm the unit, Set the document type, Review N figures). Nothing waiting is said plainly.
  3. **Being read now**: live stage progress (it polls while anything is moving); when nothing is, the upload card.
  4. **Library**: every report with its settlement bar and headline ratio; "/" filters, ↑ ↓ ↵, hover prefetch, right-click menu. Columns appear as there is room (phones: name and status).
  No reports: onboarding with "Analyse your first report" and "Explore with sample reports". Unavailable: says so, upload still offered. Loading: the page itself in placeholder form (no layout shift). The dashboard computes nothing: counts and values come from `GET /dashboard`, which reads the stored packs.
- **Sample data**: `POST /samples` (or `finintel demo seed`) runs bundled PDFs (the company_a excerpt and synthetic reports: a bank, one blocked on its unit, one waiting for its document type) through the real pipeline and marks them `is_sample`; a PDF already present (a person's upload) is never marked. They show a "Sample" tag, can be hidden (remembered per browser) and removed as a set (`DELETE /samples`, `finintel demo clear`; optimistic on screen). No model is called for samples: their commentary is extractive.
- **Data**: TanStack Query caches reports and the list; a report polls only while its stages run. **Optimistic updates are status and workflow only** (a decision shows "Processing" at once; a refusal puts the screen back and raises a notice): a figure is never shown before the server has computed it.
- **Uploads**: one path for the drop zone, sidebar and palette; a PDF dropped anywhere on the window is caught.
- **Motion**: one set of springs (Motion) for page entry, the palette, menus, toasts and the sidebar; `prefers-reduced-motion` turns them off.
- **Theme**: tokens in `globals.css` for light and dark, chosen by the system or `data-theme`; the choice is applied by an inline script before first paint.
- **Focus**: a brand focus ring (2 px plus a soft halo) on every control; text fields show focus through their container.

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

*Revised 2026-10-12 (viewer upgrade). The panel still shows one page with its highlight; the rest is how it is drawn and what opens from it.*

- **Drawing off the main thread.** A render worker runs pdf.js (parsing in-thread, drawing on an OffscreenCanvas) and returns each page as an ImageBitmap. A page asked for while the worker is still starting is drawn on the main thread, so the first page never waits; a worker that fails is reported in the console and falls back the same way. `data-render-mode` on the viewer records which thread drew the pages.
- **Pages:** a skeleton until drawn, then a fade-in; a cached page appears at once; while a zoom is still changing the existing bitmap is shown stretched and the sharp one replaces it.
- **Text:** pdf.js's own text layer (TextLayerBuilder), so selection, copy and double-click behave as native DOM text.
- **Theme:** in dark mode the page's lightness is inverted with hue kept and mapped onto the app's `--surface` and `--ink`; images on the page (recorded by pdf.js while drawing) keep their printed colours.
- **Controls:** a floating glass toolbar (fades when idle, returns on hover or focus); pinch to zoom anchored under the fingers (trackpad, Safari gestures, touch); Space-drag or middle-drag pans with momentum.
- **Keys** (while the pointer or focus is on the viewer): ← → page, ⌘/Ctrl + = − 0 zoom, ⌘/Ctrl F opens the reader's search.
- **Open document:** a full-screen reader at the same page with the same highlights: continuous pages (only those near the viewport are mounted; the next ones are drawn ahead), a sidebar with thumbnails that follow the page being read, the PDF's outline and search results; search across all pages (⌘/Ctrl F, Enter / ⇧Enter or ⌘/Ctrl G to step, matches marked on the page); ← → PageUp PageDown Home End; ⌘/Ctrl + = − 0; S toggles the sidebar; Esc closes and the panel follows to the page you were on. A context menu offers copy, search for the selection and zoom.

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
