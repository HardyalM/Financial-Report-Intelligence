/** The dashboard: the outcome first, what waits for a person, the library, and sample data. */
import type { Page } from "@playwright/test";
import { expect, loadFixture, openDashboard, routeFixtures, test } from "./support/fixtures";

const FIXTURES = ["company_a", "example_states", "liquidity_ordered_bank", "missing_unit", "liquidity_ordered_insurer"] as const;

test("the latest result leads: the engine's ratios, how its figures were settled, its citations", async ({ page }) => {
  await openDashboard(page, [...FIXTURES]);
  const spot = page.getByTestId("spotlight");
  await expect(page.getByTestId("spotlight-title")).toHaveText("company_a"); // newest ready report
  // the ratio engine's own values, formatted as on the report screen
  await expect(spot.locator("[data-ratio=operating_margin]").getByTestId("spotlight-ratio-value")).toHaveText("15.5%");
  await expect(spot.locator("[data-ratio=roce]").getByTestId("spotlight-ratio-value")).toHaveText("17.2%");
  await expect(spot.locator("[data-ratio=current_ratio]").getByTestId("spotlight-ratio-value")).toHaveText("0.76x");
  await expect(spot.locator("[data-ratio=debt_to_equity]")).toContainText("Not computed: an input is empty");
  // every current-period figure, counted by how it was settled
  const pack = (loadFixture("company_a").report as { pack: { periods: { id: string }[]; items: Record<string, { values: { period_id: string; value: number | null }[] }> } }).pack;
  const now = pack.periods[0]!.id;
  const values = Object.values(pack.items).flatMap((i) => i.values.filter((v) => v.period_id === now));
  const read = Number(await page.getByTestId("settled-read").innerText());
  const empty = Number(await page.getByTestId("settled-empty").innerText());
  expect(empty).toBe(values.filter((v) => v.value === null).length);
  expect(read).toBeLessThanOrEqual(values.length - empty);
  await expect(page.getByTestId("spotlight-commentary")).toContainText("cited passage");
  await page.getByTestId("spotlight-open").click();
  await expect(page).toHaveURL(/\/reports\/\d+$/);
});

test("what waits for a person is listed with the one action that resolves it", async ({ page }) => {
  await openDashboard(page, [...FIXTURES]);
  const queue = page.getByTestId("waiting");
  await expect(queue.getByTestId("waiting-action")).toContainText(["Confirm the unit", "Set the document type"]);
  await queue.getByRole("link", { name: /Confirm the unit/ }).click();
  await expect(page.getByTestId("report-header")).toBeVisible();
  await expect(page.getByTestId("status-badge")).toHaveText("Needs unit confirmation");
});

test("nothing waiting is said plainly", async ({ page }) => {
  await openDashboard(page, ["company_a"]);
  await expect(page.getByTestId("waiting-empty")).toContainText("Nothing is waiting for you");
});

test("sample reports are marked, can be hidden (remembered) and removed at once", async ({ page }) => {
  await openDashboard(page, [...FIXTURES], { samples: ["liquidity_ordered_bank", "missing_unit"] });
  const rows = page.getByTestId("report-row");
  await expect(rows).toHaveCount(5);
  await expect(page.getByTestId("report-list").getByTestId("sample-tag")).toHaveCount(2);
  await page.getByTestId("samples-toggle").click(); // hide
  await expect(rows).toHaveCount(3);
  await page.reload();
  await expect(page.getByTestId("report-row")).toHaveCount(3); // remembered
  await page.getByTestId("samples-toggle").click(); // show again
  await expect(page.getByTestId("report-row")).toHaveCount(5);

  // Remove: optimistic (gone at once), then the server's answer.
  let release: () => void = () => undefined;
  const gate = new Promise<void>((r) => (release = r));
  await page.route("**/api/samples", async (route) => {
    await gate;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ added: [], skipped: [], removed: [3, 5] }) });
  });
  await page.getByTestId("samples-remove").click();
  await expect(page.getByTestId("report-row")).toHaveCount(3); // before the server answered
  release();
  await expect(page.getByTestId("toast")).toContainText("Sample reports removed");
});

test("an empty workspace offers sample reports in one click", async ({ page }) => {
  let posted = false;
  await page.route("**/api/dashboard", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ reports: [], has_samples: false }) }),
  );
  await page.route("**/api/reports", (r) => r.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/samples", (r) => {
    posted = r.request().method() === "POST";
    return r.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ added: [7, 8], skipped: [], removed: [] }) });
  });
  await page.goto("/");
  await page.getByTestId("samples-add").click();
  await expect(page.getByTestId("toast")).toContainText("Sample reports added");
  expect(posted).toBeTruthy();
});

async function cls(page: Page): Promise<number> {
  return page.evaluate(
    () =>
      new Promise<number>((resolve) => {
        let total = 0;
        const o = new PerformanceObserver((l) => {
          for (const e of l.getEntries() as (PerformanceEntry & { value: number; hadRecentInput: boolean })[]) if (!e.hadRecentInput) total += e.value;
        });
        o.observe({ type: "layout-shift", buffered: true });
        setTimeout(() => (o.disconnect(), resolve(total)), 300);
      }),
  );
}

test("the skeleton is the page: no layout shift when the data arrives", async ({ page }) => {
  await routeFixtures(page, [...FIXTURES]);
  let release: () => void = () => undefined;
  const gate = new Promise<void>((r) => (release = r));
  await page.route("**/api/dashboard", async (route) => {
    await gate;
    await route.fallback();
  });
  await page.goto("/");
  await expect(page.getByTestId("dashboard-skeleton")).toBeVisible();
  release();
  await expect(page.getByTestId("dashboard")).toBeVisible();
  await expect(page.getByTestId("spotlight-title")).toBeVisible();
  expect(await cls(page)).toBeLessThan(0.05);
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test("the dashboard fits the width and keeps its order", async ({ page }) => {
    await openDashboard(page, [...FIXTURES]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
    const top = async (id: string) => (await page.getByTestId(id).boundingBox())!.y;
    expect(await top("spotlight")).toBeLessThan(await top("waiting"));
    expect(await top("waiting")).toBeLessThan(await top("report-list"));
  });
});
