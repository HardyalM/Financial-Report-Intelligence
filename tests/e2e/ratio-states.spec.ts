/** M7.1: every ratio-card state in UI.md section 5 renders from the fixture packs. */
import { expect, openReport, test } from "./support/fixtures";

const card = (page: import("@playwright/test").Page, ratio: string) => page.locator(`[data-ratio=${ratio}]`);

test("K1 OK: value, change, formula, inputs with page chips, help text", async ({ page }) => {
  await openReport(page, "company_a");
  const c = card(page, "current_ratio");
  await expect(c).toHaveAttribute("data-testid", "ratio-card-state-K1");
  await expect(c.getByTestId("ratio-value")).toHaveText("0.76x");
  await expect(c.getByTestId("ratio-formula")).toHaveText("Current assets ÷ Current liabilities");
  await expect(c.getByTestId("ratio-inputs")).toContainText("19,194");
  await expect(c.getByTestId("input-page-chip").first()).toHaveText("p.143");
  await expect(c).toContainText("Year-end balances; seasonal businesses may differ within the year.");
});

test("K2 OK with flag: the value is shown with 'Not meaningful: negative equity'", async ({ page }) => {
  await openReport(page, "example_states");
  const c = card(page, "debt_to_equity");
  await expect(c).toHaveAttribute("data-testid", "ratio-card-state-K2");
  await expect(c.getByTestId("ratio-value")).toHaveText("−20.14x");
  await expect(c.getByTestId("ratio-flag")).toHaveText("Not meaningful: negative equity");
  await c.getByTestId("debt-split-toggle").click();
  await expect(c.getByTestId("debt-split")).toContainText("Lease liabilities (non-current)");
  await expect(c.getByTestId("debt-split")).toContainText("2,150");
});

test("K3 missing input: a link that scrolls to and highlights the row", async ({ page }) => {
  await openReport(page, "example_not_found");
  const c = card(page, "roce");
  await expect(c).toHaveAttribute("data-testid", "ratio-card-state-K3");
  const link = c.getByTestId("ratio-missing-input");
  await expect(link).toHaveText("Needs total assets: not found");
  await link.click();
  await expect(page.locator("#row-total_assets")).toHaveClass(/row-flash/);
  await expect(page.locator("#row-total_assets")).toBeInViewport();
});

test("K3 names the state of each missing input (review, model suggestion)", async ({ page }) => {
  await openReport(page, "example_states");
  await expect(card(page, "operating_margin").getByTestId("ratio-missing-input")).toHaveText(
    "Needs revenue: suggested by model, not confirmed",
  );
  await expect(card(page, "current_ratio").getByTestId("ratio-missing-input")).toHaveText(
    "Needs current assets: needs review",
  );
});

test("K4 not applicable: 'Not applicable to banks' on all four cards", async ({ page }) => {
  await openReport(page, "liquidity_ordered_bank");
  await expect(page.getByTestId("ratio-card-state-K4")).toHaveCount(4);
  for (const c of await page.getByTestId("ratio-card-state-K4").all()) {
    await expect(c).toContainText("Not applicable to banks");
  }
});

test("K5 withheld: document type unclear, with the way to confirm it", async ({ page }) => {
  await openReport(page, "liquidity_ordered_insurer");
  await expect(page.getByTestId("ratio-card-state-K5")).toHaveCount(4);
  const first = page.getByTestId("ratio-card-state-K5").first();
  await expect(first).toContainText("Document type unclear: confirm to show ratios");
  await first.getByTestId("confirm-document-type").click();
  await expect(page.getByTestId("banner-document-type")).toBeInViewport();
});

test("K6 uses a manual input: the K1 display plus the inherited badge", async ({ page }) => {
  await openReport(page, "example_not_found");
  const c = card(page, "current_ratio");
  await expect(c).toHaveAttribute("data-testid", "ratio-card-state-K1");
  await expect(c.getByTestId("ratio-card-state-K6")).toHaveText("Uses a manual figure");
  await expect(c.getByTestId("ratio-value")).toHaveText("0.89x");
  await expect(c.getByTestId("ratio-inputs")).toContainText("Manual");
});
