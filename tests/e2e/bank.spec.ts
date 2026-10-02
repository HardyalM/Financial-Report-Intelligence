/** M8.1: the bank golden report (company_b) from the real pipeline (tests/e2e/fixtures/api). */
import { expect, openReport, test } from "./support/fixtures";

test("the bank report shows 'Not applicable to banks' on all four ratio cards", async ({ page }) => {
  await openReport(page, "company_b");
  await expect(page.getByTestId("document-type-badge")).toHaveText("Bank");
  const cards = page.getByTestId("ratio-card-state-K4");
  await expect(cards).toHaveCount(4);
  for (const card of await cards.all()) {
    await expect(card).toContainText("Not applicable to banks");
    await expect(card.getByTestId("ratio-value")).toHaveCount(0); // never a number
  }
});

test("bank lines are shown as printed and never stand in for revenue or operating profit", async ({ page }) => {
  await openReport(page, "company_b");
  const value = (item: string) => page.locator(`#row-${item} td[data-period=FY2024]`);
  await expect(value("net_interest_income")).toHaveText("12,277");
  await expect(value("total_income")).toHaveText("34,281");
  await expect(value("profit_before_tax")).toHaveText("5,971");
  await expect(value("total_assets")).toHaveText("906,697");
  await expect(value("total_equity")).toHaveText("45,888");
  for (const item of ["revenue", "operating_profit", "current_assets", "current_liabilities", "total_debt"]) {
    const row = page.locator(`#row-${item}`);
    await expect(row).toHaveAttribute("data-testid", "figure-row-state-R9");
    await expect(row).toContainText("Not applicable");
    await expect(row.locator("td[data-period=FY2024]")).toHaveText("—");
  }
  await expect(page.locator("#row-revenue")).toContainText("net interest income and total income, not revenue");
  await expect(page.locator("#row-total_debt")).toContainText("customer deposits are not corporate debt");
  await expect(page.getByTestId("numbers-snapshot")).toHaveCount(0);
});
