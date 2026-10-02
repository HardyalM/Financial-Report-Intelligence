/** M7.1: the report screen renders company_a from a precomputed API fixture. */
import { expect, openReport, test } from "./support/fixtures";

test("the report screen renders company_a from the precomputed fixture", async ({ page }) => {
  const body = await openReport(page, "company_a");
  const report = body.report as unknown as { pack: { items: Record<string, unknown> } };

  await expect(page.getByTestId("report-title")).toHaveText("company_a");
  await expect(page.getByTestId("unit-badge")).toContainText("€m EUR");
  await expect(page.getByTestId("status-badge")).toHaveText("Ready");
  await expect(page.getByTestId("reduced-verification-badge")).toBeVisible();

  const table = page.getByTestId("figures-table");
  await expect(table.getByRole("columnheader", { name: "FY2024" })).toBeVisible();
  await expect(table.getByRole("columnheader", { name: "FY2023" })).toBeVisible();
  const revenue = page.locator("#row-revenue");
  await expect(revenue).toContainText("Revenue");
  await expect(revenue.locator("td[data-period=FY2024]")).toHaveText("60,761");
  await expect(revenue.locator("td[data-period=FY2023]")).toHaveText("59,604");
  await expect(revenue.getByTestId("page-chip")).toHaveText("p.141");
  await expect(revenue.getByTestId("note-chip")).toHaveText("Note 2");
  await expect(revenue.locator("td").last()).toHaveText("+1.9%");
  // Every item the pack carries is a row, except the debt components shown under total debt.
  const rows = Object.keys(report.pack.items).filter((k) => !/^(borrowings|lease_liabilities)_/.test(k));
  await expect(table.locator("tr[data-item]")).toHaveCount(rows.length);

  await expect(page.locator("[data-ratio]")).toHaveCount(4);
  const margin = page.locator("[data-ratio=operating_margin]");
  await expect(margin.getByTestId("ratio-value")).toHaveText("15.5%");
  await expect(margin.getByTestId("ratio-change")).toHaveText("−0.9 pp");
  await expect(margin.getByTestId("ratio-formula")).toHaveText("Operating profit ÷ Revenue");
  await expect(page.locator("[data-ratio=roce]").getByTestId("ratio-value")).toHaveText("17.2%");
  await expect(page.locator("[data-ratio=current_ratio]").getByTestId("ratio-value")).toHaveText("0.76x");

  await expect(page.getByTestId("numbers-snapshot")).toContainText("Revenue €60.8bn (+1.9%)");
  await expect(page.getByTestId("executive-summary")).toBeVisible();
  await expect(page.locator("[data-topic]")).toHaveCount(4);
  await expect(page.getByTestId("citation-marker").first()).toBeVisible();
});

test("the footer says it is a research aid on every view", async ({ page }) => {
  await openReport(page, "company_a");
  await expect(page.getByTestId("footer")).toContainText("Research aid. Not investment advice.");
  await page.goto("/");
  await expect(page.getByTestId("footer")).toContainText("Research aid. Not investment advice.");
});

test("no buy, sell or hold language appears on the screen", async ({ page }) => {
  await openReport(page, "company_a");
  const text = (await page.locator("body").innerText()).toLowerCase();
  for (const word of [" buy ", " sell ", " hold ", "undervalued", "recommend", "attractive", "ai thinks", "insights"]) {
    expect(text, word).not.toContain(word);
  }
});

test("selecting a page chip shows the figure's provenance", async ({ page }) => {
  await openReport(page, "company_a");
  await expect(page.getByTestId("evidence-empty")).toBeVisible();
  await page.locator("#row-revenue").getByTestId("page-chip").click();
  const card = page.getByTestId("provenance-card");
  await expect(card).toContainText("Revenue");
  await expect(card).toContainText("Printed as “Turnover”");
  await expect(card).toContainText("60,761");
  await expect(card).toContainText("PDF p. 141 · printed p. 138");
  await expect(card).toContainText("text layer");
});
