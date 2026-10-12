/** Deleting a report: confirmed (it cannot be undone), immediate, and honest when refused. */
import { expect, openDashboard, openReport, test } from "./support/fixtures";

const FIXTURES = ["company_a", "example_states", "missing_unit"] as const;

test("delete from a row: a confirmation first; Cancel (or Esc) keeps it, Delete removes it at once", async ({ page }) => {
  await openDashboard(page, [...FIXTURES]);
  const rows = page.getByTestId("report-row");
  await expect(rows).toHaveCount(3);
  const row = rows.filter({ hasText: "example_states" });

  await row.click({ button: "right" });
  await page.getByRole("menuitem", { name: "Delete report…" }).click();
  const dialog = page.getByTestId("confirm-dialog");
  await expect(dialog).toContainText("Delete “example_states”?");
  await expect(dialog).toContainText("can’t be undone");
  await expect(page.getByTestId("confirm-cancel")).toBeFocused(); // Enter never deletes by accident
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(rows).toHaveCount(3);

  await row.click({ button: "right" });
  await page.getByRole("menuitem", { name: "Delete report…" }).click();
  await page.getByTestId("confirm-ok").click();
  await expect(rows).toHaveCount(2);
  await expect(page.getByTestId("toast")).toContainText("Report deleted");
  await expect(page.getByTestId("sidebar").getByTestId("sidebar-report")).toHaveCount(2);
});

test("delete from the report page: its ⋯ menu, then back to the dashboard without it", async ({ page }) => {
  await openReport(page, "company_a");
  await page.getByTestId("report-actions").click();
  await page.getByRole("menuitem", { name: "Delete report…" }).click();
  await page.getByTestId("confirm-ok").click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByTestId("toast")).toContainText("Report deleted");
});

test("a refused delete puts the report back and says why", async ({ page }) => {
  await openDashboard(page, [...FIXTURES]);
  await page.route("**/api/reports/*", async (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    await route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({ detail: { code: "report_busy", message: "the index stage is running; try again when it ends" } }),
    });
  });
  const rows = page.getByTestId("report-row");
  await rows.first().click({ button: "right" });
  await page.getByRole("menuitem", { name: "Delete report…" }).click();
  await page.getByTestId("confirm-ok").click();
  await expect(page.getByTestId("toast")).toContainText("try again when it ends");
  await expect(rows).toHaveCount(3); // back
});
