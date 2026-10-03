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

test("the bank's own ratios are computed in code from the printed lines (M8.2)", async ({ page }) => {
  await openReport(page, "company_b");
  const cards = page.getByTestId("bank-ratios");
  const cti = cards.locator("[data-ratio=cost_to_income]");
  await expect(cti).toHaveAttribute("data-testid", "ratio-card-state-K1");
  await expect(cti.getByTestId("ratio-value")).toHaveText("64.4%");
  await expect(cti.getByTestId("ratio-change")).toHaveText("+6.3 pp");
  await expect(cti.getByTestId("ratio-formula")).toHaveText(
    "Operating expenses (magnitude) ÷ Total income after insurance finance",
  );
  await expect(cti.getByTestId("ratio-inputs")).toContainText("(11,601)"); // the printed sign is kept
  await expect(cti.getByTestId("ratio-inputs")).toContainText("18,003");
  const ltd = cards.locator("[data-ratio=loan_to_deposit]");
  await expect(ltd.getByTestId("ratio-value")).toHaveText("95.3%");
  // The corporate four are still there, not applicable, so their absence is explained.
  await expect(page.getByTestId("ratio-card-state-K4")).toHaveCount(4);
});

test("CET1 and net interest margin are quoted as reported, never computed (M8.2)", async ({ page }) => {
  await openReport(page, "company_b");
  const panel = page.getByTestId("reported-metrics");
  await expect(panel).toContainText("Not computed here; never used in a ratio.");
  await expect(panel.getByTestId("reported-cet1_ratio")).toContainText("FY202414.2 per cent");
  await expect(panel.getByTestId("reported-cet1_ratio")).toContainText("FY202314.6 per cent");
  await expect(panel.getByTestId("reported-cet1_ratio_pro_forma")).toContainText("13.5 per cent");
  await expect(panel.getByTestId("reported-net_interest_margin")).toContainText("2.95 per cent");
  await expect(panel.getByTestId("reported-net_interest_margin")).toContainText("“banking net interest margin”");
  await panel.getByTestId("reported-cet1_ratio").getByTestId("reported-page-chip").first().click();
  const card = page.getByTestId("provenance-card");
  await expect(card.getByTestId("reported-quote")).toContainText("CET1 capital ratio at 31 December 2024 was 14.2 per cent");
  await expect(card).toContainText("PDF p. 72 · printed p. 68");
  await expect(card.getByTestId("reported-note")).toContainText("never feeds a ratio");
});

test("a corporate report shows no reported-metrics panel", async ({ page }) => {
  await openReport(page, "company_a");
  await expect(page.getByTestId("reported-metrics")).toHaveCount(0);
  await expect(page.getByTestId("bank-ratios")).toHaveCount(0);
});
