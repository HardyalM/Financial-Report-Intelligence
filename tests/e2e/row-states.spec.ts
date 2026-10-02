/** M7.1: every key-figure row state in UI.md section 4 renders from the fixture packs. */
import { expect, openReport, test } from "./support/fixtures";

const row = (page: import("@playwright/test").Page, item: string) => page.locator(`#row-${item}`);

test("R1 published, verified: two engine families agree", async ({ page }) => {
  await openReport(page, "example_states");
  const r = row(page, "total_equity");
  await expect(r).toHaveAttribute("data-testid", "figure-row-state-R1");
  await expect(r).toContainText("Two engine families agree");
  await expect(r.locator("td[data-period=FY2025]")).toHaveText("(350)");
  await expect(r.getByTestId("page-chip")).toHaveText("p.4");
});

test("R2 published, single family: one engine family", async ({ page }) => {
  await openReport(page, "company_a");
  const r = row(page, "operating_profit");
  await expect(r).toHaveAttribute("data-testid", "figure-row-state-R2");
  await expect(r).toContainText("One engine family");
  await expect(r.locator("td[data-period=FY2024]")).toHaveText("9,400");
});

test("R3 derived: total debt lists its four lines with page chips", async ({ page }) => {
  await openReport(page, "example_states");
  const r = row(page, "total_debt");
  await expect(r).toHaveAttribute("data-testid", "figure-row-state-R3");
  await expect(r).toContainText("Derived: sum of 4 lines");
  await expect(r.locator("td[data-period=FY2025]")).toHaveText("7,050");
  await r.getByTestId("derived-expander").click();
  const parts = page.getByTestId("derived-component");
  await expect(parts).toHaveCount(4);
  await expect(parts.nth(0)).toContainText("Borrowings (current)");
  await expect(parts.nth(0).getByTestId("page-chip")).toHaveText("p.4");
  await expect(parts.nth(3)).toContainText("2,150");
});

test("R4 confirmed by you", async ({ page }) => {
  await openReport(page, "example_states");
  const r = row(page, "operating_profit");
  await expect(r).toHaveAttribute("data-testid", "figure-row-state-R4");
  await expect(r).toContainText("Confirmed by you");
  await expect(r.locator("td[data-period=FY2025]")).toHaveText("1,480");
});

test("R5 manual, not found on page: amber badge with the reason on hover", async ({ page }) => {
  await openReport(page, "example_states");
  const r = row(page, "profit_before_tax");
  await expect(r).toHaveAttribute("data-testid", "figure-row-state-R5");
  const badge = r.getByText("Manual: not found on page");
  await expect(badge).toBeVisible();
  await badge.hover();
  await expect(page.getByRole("tooltip")).toContainText("the figure is not printed on p. 3");
  await expect(page.getByRole("tooltip")).toContainText("preliminary results");
});

test("R6 needs review: the warning in words, the code only on hover", async ({ page }) => {
  await openReport(page, "example_states");
  const r = row(page, "net_income");
  await expect(r).toHaveAttribute("data-testid", "figure-row-state-R6");
  await expect(r).toContainText("Needs review (1 candidate)");
  await expect(r).toContainText("Profit before tax less tax doesn’t equal profit for the year (off by 10 in FY2025).");
  await expect(r).not.toContainText("net_income_chain");
  await expect(r.locator("td[data-period=FY2025]")).toHaveText("—");
});

test("R7 suggested by model: the row label, never a number", async ({ page }) => {
  await openReport(page, "example_states");
  const r = row(page, "revenue");
  await expect(r).toHaveAttribute("data-testid", "figure-row-state-R7");
  await expect(r).toContainText("Suggested by model: confirm?");
  await expect(r).toContainText("“Sales of goods” on p. 3");
  await expect(r).not.toContainText("12,345");
  await expect(r.locator("td[data-period=FY2025]")).toHaveText("—");
});

test("R8 not found: where we looked", async ({ page }) => {
  await openReport(page, "example_not_found");
  const r = row(page, "total_assets");
  await expect(r).toHaveAttribute("data-testid", "figure-row-state-R8");
  await expect(r).toContainText("Not found");
  await expect(r.getByTestId("where-we-looked")).toHaveText(
    "Searched the consolidated balance sheet (p. 4) for total assets.",
  );
});

test("R8 not found with the extractor's reason (company_a total debt)", async ({ page }) => {
  await openReport(page, "company_a");
  const r = row(page, "total_debt");
  await expect(r).toHaveAttribute("data-testid", "figure-row-state-R8");
  await expect(r).toContainText("can’t be separated out");
});

test("R9 not applicable: no current/non-current split", async ({ page }) => {
  await openReport(page, "liquidity_ordered_insurer");
  const r = row(page, "current_assets");
  await expect(r).toHaveAttribute("data-testid", "figure-row-state-R9");
  await expect(r).toContainText("Not applicable: the balance sheet has no current/non-current split");
});

test("R10 blocked: the whole table is greyed until the unit is confirmed", async ({ page }) => {
  await openReport(page, "missing_unit");
  await expect(page.getByTestId("figure-row-state-R10").first()).toBeVisible();
  await expect(page.getByTestId("figures-table")).toContainText("Confirm the unit to see figures");
  await expect(page.getByTestId("banner-unit")).toBeVisible();
  await expect(page.locator("[data-testid=figures-table] td").filter({ hasText: /\d/ })).toHaveCount(0);
  for (const c of await page.locator("[data-ratio]").all()) {
    await expect(c).toContainText("Withheld until the unit is confirmed");
  }
});
