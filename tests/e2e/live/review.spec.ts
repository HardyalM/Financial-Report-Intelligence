/**
 * M7.3 end to end, against the real API and worker (tests/e2e/live_server.py; E2E_LIVE=1).
 * Each test uploads its own synthetic PDF, so no test depends on another's report.
 */
import path from "node:path";
import { expect, type Page, test } from "@playwright/test";

const PDFS = path.resolve(__dirname, "..", "fixtures", "pdfs");
// In file order: the refusal test must see no override before point-to-page adds one to the
// same report (uploading the same file again returns the same report).
test.describe.configure({ mode: "serial" });
const READY = 120_000;

async function upload(page: Page, name: string): Promise<number> {
  await page.goto("/");
  await page.getByTestId("upload-input").setInputFiles(path.join(PDFS, name));
  await page.waitForURL(/\/reports\/\d+$/);
  return Number(page.url().split("/").pop());
}

async function overrides(page: Page, id: number): Promise<unknown[]> {
  const r = await page.request.get(`/api/reports/${id}/overrides`);
  expect(r.ok()).toBeTruthy();
  return (await r.json()) as unknown[];
}

test("a small synthetic PDF moves through the progress stages to ready", async ({ page }) => {
  await upload(page, "example_stale.pdf");
  const stepper = page.getByTestId("progress-stepper");
  await expect(stepper).toBeVisible();
  // Seen moving: at least one stage running while later ones wait.
  await expect(stepper.locator("[data-state=running]").first()).toBeVisible();
  await expect(stepper.locator("[data-state=waiting]").first()).toBeVisible();
  await expect(page.getByTestId("status-badge")).toHaveText("Ready", { timeout: READY });
  await expect(stepper).toHaveCount(0);
  await expect(page.locator("#row-revenue td[data-period=FY2025]")).toHaveText("12,500");
  await expect(page.getByTestId("commentary")).toBeVisible();
});

test("entering a value that is not on the page is refused and nothing is saved", async ({ page }) => {
  const id = await upload(page, "example_not_found.pdf");
  await expect(page.getByTestId("status-badge")).toHaveText("Ready", { timeout: READY });
  const row = page.locator("#row-total_assets");
  await expect(row).toHaveAttribute("data-testid", "figure-row-state-R8");
  await row.getByTestId("open-review").click();
  const panel = page.getByTestId("review-panel");
  await panel.getByTestId("enter-from-page").click();
  await panel.getByTestId("enter-page").fill("4");
  await panel.getByTestId("enter-raw").fill("9,950");
  await panel.getByTestId("enter-value").fill("9950");
  await panel.getByTestId("enter-submit").click();
  await expect(panel.getByTestId("review-refusal")).toHaveText(
    "That text isn’t on page 4. Check the page number or select the figure on the page.",
  );
  expect(await overrides(page, id)).toEqual([]);
  await page.reload();
  await expect(page.locator("#row-total_assets")).toHaveAttribute("data-testid", "figure-row-state-R8");
});

test("pointing to the statement page re-reads it and the report comes back ready", async ({ page }) => {
  const id = await upload(page, "example_not_found.pdf");
  await expect(page.getByTestId("status-badge")).toHaveText("Ready", { timeout: READY });
  await page.locator("#row-total_assets").getByTestId("open-review").click();
  const form = page.getByTestId("point-to-page");
  await expect(form).toContainText("Point to the consolidated balance sheet");
  await form.getByTestId("point-page").fill("4");
  await form.getByTestId("point-submit").click();
  // The re-read runs in the worker: the stepper shows it, then the report is ready again.
  await expect(page.getByTestId("progress-stepper")).toBeVisible();
  await expect(page.getByTestId("status-badge")).toHaveText("Ready", { timeout: READY });
  await expect(page.getByTestId("progress-stepper")).toHaveCount(0);
  await expect.poll(async () => (await overrides(page, id)).map((o) => (o as { action: string }).action)).toEqual([
    "statement_location",
  ]);
  const report = await (await page.request.get(`/api/reports/${id}`)).json();
  expect(report.pack_version).toBe(2);
  expect(report.status).toBe("ready");
});

test("document type, then accepting a candidate shows Confirmed by you, then the stale banner", async ({ page }) => {
  const id = await upload(page, "example_states.pdf");
  await expect(page.getByTestId("status-badge")).toHaveText("Needs document type", { timeout: READY });
  await expect(page.getByTestId("ratio-card-state-K5")).toHaveCount(4);
  const choice = page.getByTestId("document-type-form");
  await choice.getByText("Corporate").click();
  await choice.getByTestId("document-type-reason").fill("A retailer: revenue is printed as Sales of goods");
  await choice.getByTestId("document-type-submit").click();
  await expect(page.getByTestId("progress-stepper")).toBeVisible();
  await expect(page.getByTestId("status-badge")).toHaveText("Ready", { timeout: READY });
  await expect(page.getByTestId("progress-stepper")).toHaveCount(0);
  await expect(page.getByTestId("ratio-card-state-K5")).toHaveCount(0);
  await expect(page.getByTestId("banner-stale")).toHaveCount(0);

  const row = page.locator("#row-net_income");
  await expect(row).toHaveAttribute("data-testid", "figure-row-state-R6");
  await row.getByTestId("open-review").click();
  const panel = page.getByTestId("review-panel");
  // Accepting a candidate (EXTRACTION 6): the review row comes from extraction itself.
  const candidates = panel.getByTestId("review-candidates");
  await expect(candidates).toContainText("825");
  await candidates.getByTestId("use-candidate").click();

  await expect(row).toHaveAttribute("data-testid", "figure-row-state-R4");
  await expect(row).toContainText("Confirmed by you");
  await expect(row.locator("td[data-period=FY2025]")).toHaveText("825");
  await expect(page.getByTestId("banner-stale")).toBeVisible();
  await expect(page.getByTestId("commentary-stale")).toBeVisible();
  const saved = (await overrides(page, id)) as { action: string; anchored: boolean }[];
  expect(saved.map((o) => [o.action, o.anchored])).toEqual([
    ["document_type", true],
    ["accept_candidate", true],
  ]);
});

test("the unit-confirmation dialog unblocks a report with no unit printed", async ({ page }) => {
  await upload(page, "missing_unit.pdf");
  const dialog = page.getByTestId("unit-dialog");
  await expect(dialog).toBeVisible({ timeout: READY });
  await expect(page.getByTestId("figure-row-state-R10").first()).toBeAttached();
  await expect(dialog.getByTestId("pdf-viewer")).toHaveAttribute("data-rendered-page", "2", { timeout: 15_000 });
  await dialog.getByTestId("unit-currency").selectOption("GBP");
  await dialog.getByTestId("unit-scale-1000000").check();
  await expect(dialog.getByTestId("unit-evidence")).toContainText("PDF p. 2");
  await dialog.getByTestId("unit-confirm").click();
  await expect(dialog).toHaveCount(0, { timeout: READY });
  await expect(page.getByTestId("status-badge")).toHaveText("Ready", { timeout: READY });
  await expect(page.getByTestId("unit-confirmed-badge")).toHaveText("Unit confirmed manually");
  await expect(page.getByTestId("unit-badge")).toContainText("£m GBP");
  await expect(page.getByTestId("figure-row-state-R10")).toHaveCount(0);
});
