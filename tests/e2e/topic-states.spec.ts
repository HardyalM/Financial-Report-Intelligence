/** M7.2: every commentary topic state renders from a fixture (UI.md section 7). */
import { expect, openReport, test } from "./support/fixtures";

test("ok: paragraphs with citation markers", async ({ page }) => {
  await openReport(page, "company_a");
  const ok = page.getByTestId("topic-state-ok");
  await expect(ok).toHaveCount(4);
  await expect(ok.first().getByTestId("citation-marker").first()).toBeVisible();
  await expect(page.getByTestId("extractive-label")).toHaveCount(0);
});

test("insufficient_evidence: says there isn't enough to comment on", async ({ page }) => {
  await openReport(page, "liquidity_ordered_bank");
  const topic = page.getByTestId("topic-state-insufficient_evidence").first();
  await expect(topic).toContainText("There isn’t enough in the report to comment on this topic.");
});

test("validation_failed: withheld, with the count and the reasons on hover", async ({ page }) => {
  await openReport(page, "example_failed");
  const topic = page.locator("[data-topic=revenue_drivers]");
  await expect(topic).toHaveAttribute("data-testid", "topic-state-validation_failed");
  const text = topic.getByTestId("validation-failed-text");
  await expect(text).toHaveText("Commentary withheld: it failed evidence checks (1 paragraph removed).");
  await text.hover();
  await expect(page.getByRole("tooltip")).toContainText("it typed a number instead of using a code-rendered figure");
  await expect(page.getByRole("tooltip")).toContainText("it used advice language");
  await expect(page.locator("[data-topic=strategic_risks]")).toContainText("Commentary withheld: it failed evidence checks.");
  // The model's text never reaches the screen.
  await expect(page.locator("body")).not.toContainText("investors should buy");
});

test("extractive: labelled, verbatim passages with citations", async ({ page }) => {
  await openReport(page, "example_states");
  await expect(page.getByTestId("extractive-label")).toHaveText("Extractive summary: no generated text");
  const topic = page.locator("[data-topic=revenue_drivers]");
  await expect(topic).toHaveAttribute("data-testid", "topic-state-ok");
  await expect(topic.getByTestId("citation-marker").first()).toBeVisible();
});

test("stale: figures changed since the commentary was written", async ({ page }) => {
  await openReport(page, "example_stale");
  await expect(page.getByTestId("commentary-stale")).toContainText("Figures changed since this commentary was written");
  await expect(page.getByTestId("banner-stale")).toBeVisible();
  await expect(page.locator("#row-current_assets")).toHaveAttribute("data-testid", "figure-row-state-R4");
});
