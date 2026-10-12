/** The app shell: dashboard, sidebar, command palette, theme, keyboard, prefetch, optimism. */
import type { Page } from "@playwright/test";
import { expect, openDashboard, openReport, routeFixtures, test } from "./support/fixtures";

const FIXTURES = ["company_a", "example_states", "liquidity_ordered_insurer", "missing_unit"] as const;

async function cumulativeLayoutShift(page: Page): Promise<number> {
  return page.evaluate(
    () =>
      new Promise<number>((resolve) => {
        let total = 0;
        const o = new PerformanceObserver((list) => {
          for (const e of list.getEntries() as (PerformanceEntry & { value: number; hadRecentInput: boolean })[]) {
            if (!e.hadRecentInput) total += e.value;
          }
        });
        o.observe({ type: "layout-shift", buffered: true });
        setTimeout(() => (o.disconnect(), resolve(total)), 300);
      }),
  );
}

test("the dashboard lists every report with its status and what waits for a person", async ({ page }) => {
  await openDashboard(page, [...FIXTURES]);
  const rows = page.getByTestId("report-row");
  await expect(rows).toHaveCount(4);
  await expect(page.getByTestId("filter-all")).toContainText("4");
  await page.getByTestId("filter-waiting").click();
  // Waiting = a status that needs a person (document type, unit) or open review items.
  const waiting = page.getByTestId("filter-waiting");
  const n = Number((await waiting.innerText()).match(/\d+/)![0]);
  await expect(rows).toHaveCount(n);
  const statuses = await page.getByTestId("report-row-status").allInnerTexts();
  expect(statuses).toEqual(expect.arrayContaining(["Needs document type", "Needs unit"]));
  await page.getByTestId("filter-all").click();
  await page.keyboard.press("/");
  await expect(page.getByTestId("dashboard-filter")).toBeFocused();
  await page.keyboard.type("example");
  await expect(rows).toHaveCount(1);
});

test("keyboard only: filter, arrow to a report, Enter opens it", async ({ page }) => {
  await openDashboard(page, [...FIXTURES]);
  await page.keyboard.press("/");
  await page.keyboard.press("ArrowDown");
  await expect(page.getByTestId("report-row").first()).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByTestId("report-row").nth(1)).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/reports\/\d+$/);
  await expect(page.getByTestId("report-header")).toBeVisible();
});

test("hovering a report fetches it before the click, so it opens without a skeleton", async ({ page }) => {
  const [first] = await openDashboard(page, [...FIXTURES]);
  const fetched = page.waitForRequest((r) => r.url().endsWith(`/api/reports/${first!.report.id}`));
  await page.getByTestId("report-row").first().hover();
  await fetched; // prefetched on hover
  await page.getByTestId("report-row").first().click();
  await expect(page.getByTestId("report-header")).toBeVisible();
  await expect(page.locator("[aria-busy=true]")).toHaveCount(0);
});

test("the command palette finds a report by name and opens it from the keyboard", async ({ page }) => {
  await openDashboard(page, [...FIXTURES]);
  await page.keyboard.press("ControlOrMeta+k");
  const palette = page.getByTestId("command-palette");
  await expect(palette).toBeVisible();
  await expect(page.getByTestId("palette-input")).toBeFocused();
  await expect(palette.getByRole("group", { name: "Recent" })).toBeVisible();
  await page.keyboard.type("states");
  await expect(page.getByTestId("palette-item").first()).toContainText("example_states");
  await page.keyboard.press("Enter");
  await expect(palette).toHaveCount(0);
  await expect(page).toHaveURL(/\/reports\/\d+$/);
  await expect(page.getByTestId("breadcrumbs")).toContainText("example_states");
});

test("the palette says when nothing matches and offers the next step", async ({ page }) => {
  await openDashboard(page, [...FIXTURES]);
  await page.keyboard.press("ControlOrMeta+k");
  await page.keyboard.type("zzzzqqq");
  await expect(page.getByTestId("palette-empty")).toContainText("Nothing matches");
  await expect(page.getByTestId("palette-empty").getByRole("button", { name: "Analyse a new report" })).toBeVisible();
  await page.keyboard.press("Escape"); // clears the query
  await page.keyboard.press("Escape"); // closes
  await expect(page.getByTestId("command-palette")).toHaveCount(0);
});

test("the sidebar collapses to an icon rail, remembers it, and lists reports", async ({ page }) => {
  await openDashboard(page, [...FIXTURES]);
  const sidebar = page.getByTestId("sidebar");
  await expect(sidebar.getByTestId("sidebar-report")).toHaveCount(4);
  await page.keyboard.press("ControlOrMeta+\\");
  await expect(sidebar).toHaveAttribute("data-collapsed", "true");
  await page.reload();
  await expect(page.getByTestId("sidebar")).toHaveAttribute("data-collapsed", "true");
  await page.keyboard.press("ControlOrMeta+\\");
  await expect(page.getByTestId("sidebar")).toHaveAttribute("data-collapsed", "false");
});

test("a report row has a context menu with keyboard-style hints", async ({ page }) => {
  await openDashboard(page, [...FIXTURES]);
  await page.getByTestId("report-row").first().click({ button: "right" });
  const menu = page.getByRole("menu");
  await expect(menu).toBeVisible();
  await expect(menu.getByRole("menuitem")).toContainText(["Open", "Open in a new tab", "Copy link"]);
  await page.keyboard.press("Escape");
  await expect(menu).toHaveCount(0);
});

test("the theme toggle switches to dark, and the choice is applied before first paint on reload", async ({ page }) => {
  await openDashboard(page, [...FIXTURES]);
  await page.getByTestId("theme-toggle").getByRole("radio", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload({ waitUntil: "commit" });
  // set by the inline boot script, before React has hydrated
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByTestId("dashboard")).toBeVisible();
  await expect(page.getByTestId("theme-toggle").getByRole("radio", { name: "Dark" })).toHaveAttribute("aria-checked", "true");
  await page.getByTestId("theme-toggle").getByRole("radio", { name: "Match system" }).click();
  await expect(page.locator("html")).not.toHaveAttribute("data-theme", /./);
});

test("with no reports, the dashboard is an onboarding page with one-click actions", async ({ page }) => {
  await page.route("**/api/reports", (r) => r.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.goto("/");
  await expect(page.getByTestId("onboarding")).toBeVisible();
  await expect(page.getByRole("button", { name: "Analyse your first report" })).toBeVisible();
  await expect(page.getByTestId("upload-dropzone")).toBeVisible();
  await expect(page.getByTestId("reports-unavailable")).toHaveCount(0);
});

test("if the list can't be fetched, the page says so and still offers upload", async ({ page }) => {
  await page.route("**/api/reports", (r) => r.fulfill({ status: 503, contentType: "application/json", body: "{}" }));
  await page.goto("/");
  await expect(page.getByTestId("reports-unavailable")).toBeVisible();
  await expect(page.getByTestId("upload-dropzone")).toBeVisible();
});

test("opening a report cold causes no layout shift", async ({ page }) => {
  await openReport(page, "example_states");
  await expect(page.getByTestId("figures-table")).toBeVisible();
  expect(await cumulativeLayoutShift(page)).toBeLessThan(0.02);
});

test("a decision shows as processing at once, and is put back with a notice if refused", async ({ page }) => {
  await routeFixtures(page, ["liquidity_ordered_insurer"]);
  let release: () => void = () => undefined;
  const gate = new Promise<void>((r) => (release = r));
  await page.route("**/api/reports/*/document-type", async (route) => {
    await gate; // the server is slow...
    await route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({ detail: { code: "refused", message: "not allowed for this report" } }),
    });
  });
  const { report } = (await import("./support/fixtures")).loadFixture("liquidity_ordered_insurer");
  await page.goto(`/reports/${report.id}`);
  const badge = page.getByTestId("status-badge");
  await expect(badge).toHaveText("Needs document type");
  await page.getByTestId("document-type-corporate").check({ force: true });
  await page.getByTestId("document-type-reason").fill("an insurer's group accounts");
  await page.getByTestId("document-type-submit").click();
  await expect(badge).toHaveText("Processing"); // ...but the screen has already moved on
  release();
  await expect(page.getByTestId("toast")).toContainText("not allowed for this report");
  await expect(badge).toHaveText("Needs document type"); // rolled back
});
