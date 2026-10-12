/** Fluid interaction (apple-design): closing the source, sheets, rubber-banding, swipes. */
import type { Page } from "@playwright/test";
import { expect, openReport, test } from "./support/fixtures";

const panel = (page: Page) => page.getByTestId("evidence-panel");

async function openEquity(page: Page) {
  await openReport(page, "example_states");
  await page.locator("#row-total_equity").getByTestId("page-chip").click();
  await expect(page.getByTestId("pdf-viewer")).toHaveAttribute("data-rendered-page", "4", { timeout: 15_000 });
}

/** A drag with the mouse: down, `steps` moves over `ms`, up. */
async function drag(page: Page, from: { x: number; y: number }, dy: number, ms: number, steps = 8) {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  for (let i = 1; i <= steps; i++) {
    await page.mouse.move(from.x, from.y + (dy * i) / steps);
    await page.waitForTimeout(ms / steps);
  }
  await page.mouse.up();
}

test("the source can be closed: the × beside Open document, and Esc", async ({ page }) => {
  await openEquity(page);
  await page.getByTestId("evidence-close").click();
  await expect(page.getByTestId("evidence-empty")).toBeVisible();
  await page.locator("#row-total_equity").getByTestId("page-chip").click();
  await expect(page.getByTestId("pdf-viewer")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("evidence-empty")).toBeVisible();
});

test.describe("below 1280 px the source is a bottom sheet", () => {
  test.use({ viewport: { width: 1100, height: 820 } });

  test("tapping the dimmed page behind it closes it", async ({ page }) => {
    await openEquity(page);
    await expect(panel(page)).toBeVisible();
    await page.getByTestId("evidence-scrim").click({ position: { x: 40, y: 40 } });
    await expect(panel(page)).toHaveCount(0);
  });

  test("a short drag springs back; dragged past a third, it closes", async ({ page }) => {
    await openEquity(page);
    const handle = (await page.getByTestId("evidence-handle").boundingBox())!;
    const grab = { x: handle.x + handle.width / 2, y: handle.y + handle.height / 2 };
    await drag(page, grab, 30, 600);
    await expect(panel(page)).toBeVisible(); // not far enough, no momentum: it springs back
    // Back at rest: no drag offset left on the sheet (its height may still grow as content draws).
    await expect
      .poll(async () => panel(page).evaluate((el) => new DOMMatrix(getComputedStyle(el).transform).m42), { timeout: 4000 })
      .toBeCloseTo(0, 0);
    const height = (await panel(page).boundingBox())!.height;
    await drag(page, grab, height * 0.45, 200); // past a third of its height: it closes
    await expect(panel(page)).toHaveCount(0);
  });
});

test("pinching past 400% gives with resistance, then springs back to 400%", async ({ page }) => {
  await openEquity(page);
  const frame = page.getByTestId("pdf-viewer").locator(".overflow-auto").first();
  const box = (await frame.boundingBox())!;
  const label = page.getByTestId("pdf-viewer").getByText(/^\d+%$/);
  // A trackpad pinch arrives as ctrl+wheel; push well past the 400% limit.
  for (let i = 0; i < 40; i++) {
    await frame.dispatchEvent("wheel", {
      ctrlKey: true, deltaY: -12, clientX: box.x + box.width / 2, clientY: box.y + 120, bubbles: true, cancelable: true,
    });
  }
  const during = Number((await label.innerText()).replace("%", ""));
  expect(during).toBeGreaterThan(400); // rubber-banded past the limit, not stopped at it
  expect(during).toBeLessThan(800); // ...with resistance: far less than the raw pinch asked for
  await expect(label).toHaveText("400%", { timeout: 3000 }); // released: back to the limit
});

test("a notice can be swiped away", async ({ page }) => {
  await openEquity(page);
  await page.keyboard.press("ControlOrMeta+k");
  await page.keyboard.type("copy link");
  await page.keyboard.press("Enter");
  const toast = page.getByTestId("toast");
  await expect(toast).toBeVisible();
  const b = (await toast.boundingBox())!;
  await page.mouse.move(b.x + 40, b.y + b.height / 2);
  await page.mouse.down();
  for (let i = 1; i <= 6; i++) {
    await page.mouse.move(b.x + 40 + i * 30, b.y + b.height / 2);
    await page.waitForTimeout(12);
  }
  await page.mouse.up();
  await expect(toast).toHaveCount(0);
});

test("with more contrast requested, translucent chrome becomes solid", async ({ page }) => {
  await page.emulateMedia({ contrast: "more" });
  await openReport(page, "example_states");
  const bg = await page.getByTestId("top-bar").evaluate((el) => getComputedStyle(el).backgroundColor);
  // a solid colour: no alpha below 1 in rgb()/oklch()/lab() notation
  expect(bg).not.toMatch(/\/\s*0?\.\d+\)|rgba\([^)]*,\s*0?\.\d+\)/);
});

/** Open the palette and record its transform on every frame for its first 300 ms. */
async function paletteTransforms(page: Page): Promise<string[]> {
  return page.evaluate(async () => {
    const mac = /Mac|iPhone|iPad/.test(navigator.platform);
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: mac, ctrlKey: !mac, bubbles: true }));
    const seen: string[] = [];
    const end = performance.now() + 300;
    while (performance.now() < end) {
      await new Promise((r) => requestAnimationFrame(r));
      const el = document.querySelector<HTMLElement>("[data-testid=command-palette]");
      if (el) seen.push(getComputedStyle(el).transform);
    }
    return seen;
  });
}
const still = (t: string) => t === "none" || t === "matrix(1, 0, 0, 1, 0, 0)";

test("the palette moves as it opens; with reduced motion it only fades", async ({ page }) => {
  await openReport(page, "example_states");
  expect((await paletteTransforms(page)).some((t) => !still(t))).toBeTruthy(); // it does move normally
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("command-palette")).toHaveCount(0);
  await page.emulateMedia({ reducedMotion: "reduce" });
  const reduced = await paletteTransforms(page);
  expect(reduced.length).toBeGreaterThan(0);
  expect(reduced.every(still)).toBeTruthy(); // ...and not at all with reduced motion
});

test("click off: clicking empty space on the report puts the PDF away", async ({ page }) => {
  await openEquity(page);
  await page.locator("#row-total_equity").getByTestId("page-chip").click(); // a control: stays open
  await expect(page.getByTestId("pdf-viewer")).toBeVisible();
  await page.locator("#figures-heading").click(); // empty space (a heading, not a control)
  await expect(page.getByTestId("evidence-empty")).toBeVisible();
});

test("click off: clicking the desk around the pages closes the reader; a page does not", async ({ page }) => {
  await openEquity(page);
  await page.getByTestId("open-reader").click();
  const reader = page.getByTestId("pdf-reader");
  await expect(reader).toBeVisible();
  await reader.locator(".pdf-page").first().click({ position: { x: 30, y: 30 } }); // on a page
  await expect(reader).toBeVisible();
  const desk = (await page.getByTestId("reader-scroller").boundingBox())!;
  await page.mouse.click(desk.x + 12, desk.y + desk.height / 2); // the margin beside the pages
  await expect(reader).toHaveCount(0);
  await expect(page.getByTestId("pdf-viewer")).toBeVisible(); // back to the panel, still on the source
});
