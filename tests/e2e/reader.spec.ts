/** The PDF viewer and reader: off-thread drawing, native text, search, keys, theme. */
import type { Page } from "@playwright/test";
import { expect, openReport, originalPdf, test } from "./support/fixtures";

const viewer = (page: Page) => page.getByTestId("pdf-viewer");
const reader = (page: Page) => page.getByTestId("pdf-reader");

async function openEquityPage(page: Page) {
  await openReport(page, "example_states");
  await page.locator("#row-total_equity").getByTestId("page-chip").click();
  await expect(viewer(page)).toHaveAttribute("data-rendered-page", "4", { timeout: 15_000 });
}

test("pages are drawn in the render worker once it has started", async ({ page }) => {
  await openEquityPage(page);
  // The first pages are drawn here while the worker warms up in idle time; once it has the
  // document open, new pages are the worker's. Keep asking for pages the cache can't answer.
  const zoomIn = page.getByRole("button", { name: "Zoom in" });
  const zoomOut = page.getByRole("button", { name: "Zoom out" });
  const next = page.getByRole("button", { name: "Next page" });
  const previous = page.getByRole("button", { name: "Previous page" });
  let step = 0;
  await expect(async () => {
    step++;
    if (step % 2) {
      if (await zoomIn.isEnabled()) await zoomIn.click();
      else while (await zoomOut.isEnabled()) await zoomOut.click();
    } else if (await next.isEnabled()) await next.click();
    else await previous.click();
    await expect(viewer(page)).toHaveAttribute("data-render-mode", /^(worker|mixed)$/, { timeout: 1500 });
  }).toPass({ timeout: 30_000 });
});

test("the page text is real DOM text: a double-click selects a word natively", async ({ page }) => {
  await openEquityPage(page);
  const word = viewer(page).locator(".textLayer span", { hasText: "Consolidated" }).first();
  await expect(word).toBeAttached();
  await word.dblclick({ position: { x: 4, y: 4 } }); // its first word
  const selected = await page.evaluate(() => window.getSelection()?.toString().trim());
  expect(selected).toBe("Consolidated");
});

test("the reader opens on the cited page, with keys for pages, zoom and closing", async ({ page }) => {
  await openEquityPage(page);
  await page.getByTestId("open-reader").click();
  await expect(reader(page)).toBeVisible();
  await expect(reader(page)).toHaveAttribute("data-current-page", "4");
  await expect(reader(page).getByTestId("highlight-box").first()).toBeVisible();
  await expect(page.getByTestId("reader-page-label")).toContainText("PDF p. 4");

  await page.getByTestId("reader-scroller").focus();
  await page.keyboard.press("ArrowRight");
  await expect(reader(page)).toHaveAttribute("data-current-page", "5");
  // The thumbnail mini-map follows the page being read.
  await expect(page.getByTestId("reader-thumbnails").locator("[aria-current=page]")).toHaveAccessibleName("Page 5");

  const zoom = reader(page).getByRole("button", { name: "Fit width" });
  await expect(zoom).toHaveText("100%");
  await page.keyboard.press("ControlOrMeta+=");
  await expect(zoom).toHaveText("120%");
  await page.keyboard.press("ControlOrMeta+0");
  await expect(zoom).toHaveText("100%");

  await page.keyboard.press("Escape");
  await expect(reader(page)).toHaveCount(0);
  await expect(viewer(page)).toHaveAttribute("data-page", "5"); // the panel follows the reader
});

test("search finds every occurrence, marks it on the page and steps through matches", async ({ page }) => {
  await openEquityPage(page);
  await page.getByTestId("open-reader").click();
  await expect(reader(page)).toBeVisible();
  await page.keyboard.press("ControlOrMeta+f");
  const box = page.getByTestId("reader-search");
  await expect(box).toBeFocused();
  await box.fill("total equity");
  await expect(page.getByTestId("reader-search-count")).toHaveText(/^1 of \d+$/);
  await expect(reader(page).getByTestId("search-hit").first()).toBeVisible();
  await expect(reader(page).locator("[data-testid=search-hit][data-active=true]")).toHaveCount(1);
  const results = page.getByTestId("reader-search-results").getByRole("button");
  expect(await results.count()).toBeGreaterThan(0);
  await box.press("Enter");
  await expect(page.getByTestId("reader-search-count")).toHaveText(/^(2|1) of \d+$/);
});

test("the outline tab shows the bookmarks, or says the PDF has none", async ({ page }) => {
  await openEquityPage(page);
  await page.getByTestId("open-reader").click();
  await reader(page).getByRole("tab", { name: "Outline" }).click();
  await expect(page.getByTestId("reader-outline").or(page.getByTestId("reader-outline-empty"))).toBeVisible();
});

test("dark mode recolours the page to the app's surface, not a white sheet", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await openEquityPage(page);
  const corner = await viewer(page)
    .locator("canvas")
    .first()
    .evaluate((c: HTMLCanvasElement) => [...c.getContext("2d")!.getImageData(2, 2, 1, 1).data].slice(0, 3));
  expect(Math.max(...corner)).toBeLessThan(90); // paper is the dark surface token, not white
});

test.describe("company_a (needs the local, git-ignored PDF)", () => {
  test.skip(!originalPdf("company_a"), "fixtures/pdfs/company_a.pdf is not present (ADR-009: not committed)");

  test("a 305-page report mounts only the pages near the viewport", async ({ page }) => {
    await openReport(page, "company_a");
    await page.locator("#row-revenue").getByTestId("page-chip").click();
    await expect(viewer(page)).toHaveAttribute("data-rendered-page", "141", { timeout: 15_000 });
    await page.getByTestId("open-reader").click();
    await expect(reader(page)).toHaveAttribute("data-current-page", "141");
    const mounted = await page.getByTestId("reader-scroller").locator(".pdf-page").count();
    expect(mounted).toBeGreaterThan(0);
    expect(mounted).toBeLessThanOrEqual(6);
  });
});
