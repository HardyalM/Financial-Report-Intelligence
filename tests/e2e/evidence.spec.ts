/** M7.2: the evidence panel. Every citation and every page chip opens its source page. */
import type { Locator, Page } from "@playwright/test";
import { expect, openReport, originalPdf, test } from "./support/fixtures";

const viewer = (page: Page) => page.getByTestId("pdf-viewer");

async function expectPageWithHighlight(page: Page, expected: string) {
  await expect(viewer(page)).toHaveAttribute("data-page", expected);
  await expect(viewer(page)).toHaveAttribute("data-rendered-page", expected, { timeout: 15_000 });
  const boxes = page.getByTestId("highlight-box");
  await expect(boxes.first()).toBeVisible();
  const size = await boxes.first().boundingBox();
  expect(size && size.width > 4 && size.height > 4).toBeTruthy();
}

async function clickEveryCitation(page: Page) {
  const markers = page.getByTestId("commentary").getByTestId("citation-marker");
  const count = await markers.count();
  expect(count).toBeGreaterThan(0);
  for (let i = 0; i < count; i++) {
    const marker = markers.nth(i);
    const expected = (await marker.getAttribute("data-page"))!;
    await marker.scrollIntoViewIfNeeded();
    await marker.click();
    await expectPageWithHighlight(page, expected);
    await expect(page.getByTestId("citation-quote")).not.toBeEmpty();
  }
  return count;
}

test.describe("company_a (needs the local, git-ignored PDF)", () => {
  test.skip(!originalPdf("company_a"), "fixtures/pdfs/company_a.pdf is not present (ADR-009: not committed)");
  test.setTimeout(180_000);

  test("every citation opens citation.page with at least one highlight box", async ({ page }) => {
    const body = await openReport(page, "company_a");
    const output = (body.commentary as { output: { topics: { paragraphs: { citations: unknown[] }[] }[]; executive_summary: { bullets: { citations: unknown[] }[] } } }).output;
    const expected =
      output.topics.flatMap((t) => t.paragraphs).reduce((n, p) => n + p.citations.length, 0) +
      output.executive_summary.bullets.reduce((n, b) => n + b.citations.length, 0);
    expect(await clickEveryCitation(page)).toBe(expected);
  });

  test("every page chip opens its page, highlights the figure and shows families and checks", async ({ page }) => {
    await openReport(page, "company_a");
    await clickEveryChip(page, true);
  });

  test("a figure in the commentary selects its source figure", async ({ page }) => {
    await openReport(page, "company_a");
    await page.locator("[data-placeholder='item:revenue:FY2024']").first().click();
    await expect(page.getByTestId("provenance-card")).toContainText("Revenue");
    await expect(page.getByTestId("provenance-card")).toContainText("Printed as “Turnover”");
    await expectPageWithHighlight(page, "141");
    await expect(page.getByTestId("viewer-page-label")).toContainText("PDF p. 141 · printed p. 138");
  });
});

async function clickEveryChip(page: Page, highlight: boolean): Promise<number> {
  const chips: Locator = page.locator("[data-testid=page-chip], [data-testid=input-page-chip]");
  const count = await chips.count();
  expect(count).toBeGreaterThan(0);
  for (let i = 0; i < count; i++) {
    const chip = chips.nth(i);
    const expected = (await chip.innerText()).replace("p.", "").trim();
    await chip.scrollIntoViewIfNeeded();
    await chip.click();
    const located = (await page.getByTestId("no-position").count()) === 0;
    if (highlight && located) await expectPageWithHighlight(page, expected);
    else await expect(viewer(page)).toHaveAttribute("data-rendered-page", expected, { timeout: 15_000 });
    const families = page.getByTestId("provenance-families");
    await expect(families).toContainText(/text layer|image layout|Derived in code|Entered by a person/);
    await expect(page.getByTestId("provenance-checks")).toContainText(/✓|✗|No arithmetic check covers this line/);
  }
  return count;
}

test("every citation in a synthetic report opens its page with a highlight", async ({ page }) => {
  await openReport(page, "example_states");
  await clickEveryCitation(page);
});

test("a figure a person confirmed opens its page and says its position is not recorded", async ({ page }) => {
  await openReport(page, "example_not_found");
  await page.locator("#row-current_assets").getByTestId("page-chip").click();
  await expect(viewer(page)).toHaveAttribute("data-rendered-page", "4");
  await expect(page.getByTestId("no-position")).toContainText("set by a person");
  await expect(page.getByTestId("highlight-box")).toHaveCount(0);
});

test("every page chip in the state fixture shows the engine families and checks", async ({ page }) => {
  await openReport(page, "example_not_found");
  await page.locator("#row-total_debt").getByTestId("derived-expander").click();
  await clickEveryChip(page, true);
});

test("two engine families and a passed check are named on the provenance card", async ({ page }) => {
  await openReport(page, "example_states");
  await page.locator("#row-total_equity").getByTestId("page-chip").click();
  await expect(page.getByTestId("provenance-families")).toContainText("image layout and text layer agree");
  await expect(page.getByTestId("provenance-checks")).toContainText("Total equity = sum of");
  await expect(page.getByTestId("provenance-checks")).toContainText("✓");
});

test("a failed check is named with its difference", async ({ page }) => {
  await openReport(page, "example_states");
  await page.locator("#row-net_income").getByTestId("page-chip").click();
  await expect(page.getByTestId("provenance-checks")).toContainText("Profit for the year = profit before tax plus 1 rows");
  await expect(page.getByTestId("provenance-checks")).toContainText("(off by 10)");
});

test("the viewer pages and zooms; Esc clears the selection", async ({ page }) => {
  await openReport(page, "example_states");
  await page.locator("#row-total_equity").getByTestId("page-chip").click();
  await expectPageWithHighlight(page, "4");
  await page.getByRole("button", { name: "Previous page" }).click();
  await expect(viewer(page)).toHaveAttribute("data-rendered-page", "3");
  await expect(page.getByTestId("highlight-box")).toHaveCount(0);
  await page.getByRole("button", { name: "Next page" }).click();
  await expectPageWithHighlight(page, "4");
  const before = (await page.getByTestId("highlight-box").first().boundingBox())!;
  await page.getByRole("button", { name: "Zoom in" }).click();
  await expect(viewer(page)).toHaveAttribute("data-rendered-zoom", "150");
  const after = (await page.getByTestId("highlight-box").first().boundingBox())!;
  expect(after.width).toBeGreaterThan(before.width * 1.3);
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("evidence-empty")).toBeVisible();
});
