/**
 * M7.3 review actions against fixtures: the requests the panel sends. The live suite
 * (tests/e2e/live) runs the same flows against the real API.
 */
import { expect, loadFixture, openReport, test } from "./support/fixtures";

test("'Use this' on a candidate with a printed value sends accept_candidate with its id", async ({ page }) => {
  const body = loadFixture("example_states");
  const review = body.review as { items: unknown[] };
  // A review row as the API returns it when a candidate carries a printed value (M6.2 test shape).
  const withValue = {
    ...review,
    items: [
      ...review.items,
      { id: 41, item: "net_income", period_id: "FY2025", kind: "disagreement", status: "open",
        candidates: [{ engine: "pdfplumber", value: 825, raw_text: "825", page: 3 }] },
    ],
  };
  let sent: unknown = null;
  await openReport(page, "example_states", async (p) => {
    await p.route("**/api/reports/2/review", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(withValue) }),
    );
    await p.route("**/api/reports/2/overrides", async (route) => {
      sent = route.request().postDataJSON();
      await route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({ override_id: 1, anchored: true, pack_version: 4, pack_sha: "x", ratios_recomputed: true, stale: true, warning_codes: ["human_override"] }),
      });
    });
  });
  await page.locator("#row-net_income").getByTestId("open-review").click();
  const candidates = page.getByTestId("review-candidates");
  await expect(candidates).toContainText("825");
  await candidates.getByTestId("use-candidate").click();
  await expect.poll(() => sent).toEqual({
    action: "accept_candidate", item: "net_income", period_id: "FY2025", candidate_id: "41:0",
  });
});

test("a model suggestion offers to confirm from the page, never a number", async ({ page }) => {
  await openReport(page, "example_states");
  await page.locator("#row-revenue").getByTestId("open-review").click();
  const suggestion = page.getByTestId("review-suggestion");
  await expect(suggestion).toContainText("“Sales of goods” on p. 3");
  await suggestion.getByTestId("confirm-suggestion").click();
  await expect(page.getByTestId("enter-page")).toHaveValue("3");
  await expect(page.getByTestId("enter-value")).toHaveValue("");
});

test("review actions are not offered for a figure that needs no decision", async ({ page }) => {
  await openReport(page, "example_states");
  await page.locator("#row-total_equity").getByTestId("page-chip").click();
  await expect(page.getByTestId("provenance-card")).toBeVisible();
  await expect(page.getByTestId("review-panel")).toHaveCount(0);
});
