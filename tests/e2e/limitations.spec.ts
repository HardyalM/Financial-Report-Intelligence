/** M8.3: the limitations page is reachable from the report screen (UI.md section 1). */
import { expect, openReport, test } from "./support/fixtures";

test("the limitations page is reachable from the report screen", async ({ page }) => {
  await openReport(page, "company_a");
  await page.getByTestId("footer").getByTestId("limitations-link").click();
  await expect(page).toHaveURL(/\/limitations$/);
  const body = page.getByTestId("limitations");
  await expect(body.getByRole("heading", { level: 1 })).toHaveText("Limitations");
  await expect(body).toContainText("not investment advice");
  await expect(body).toContainText("never estimated");
  await expect(page.getByTestId("footer")).toContainText("Research aid. Not investment advice.");
});
