/**
 * Serve the precomputed API responses (tests/e2e/fixtures/api, built by build_fixtures.py) to the
 * browser. No backend runs: every /api/* call is answered here or fails the test.
 */
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { expect, type Page, test as base } from "@playwright/test";

const API_DIR = path.resolve(__dirname, "..", "fixtures", "api");
const PDF_DIR = path.resolve(__dirname, "..", "fixtures", "pdfs");
/** company_a's PDF is not committed (ADR-009 covers statement pages only): local runs only. */
export const COMPANY_A_PDF = path.resolve(__dirname, "..", "..", "..", "fixtures", "pdfs", "company_a.pdf");

export function originalPdf(name: FixtureName): string | null {
  const file = name === "company_a" ? COMPANY_A_PDF : path.join(PDF_DIR, `${name}.pdf`);
  return existsSync(file) ? file : null;
}

export type FixtureName =
  | "company_a"
  | "example_states"
  | "example_not_found"
  | "liquidity_ordered_bank"
  | "liquidity_ordered_insurer"
  | "missing_unit"
  | "example_failed"
  | "example_stale";

interface FixtureBody {
  fixture: { id: number; name: string; states: string[] };
  report: { id: number };
  commentary: unknown | null;
  review: unknown;
}

export function loadFixture(name: FixtureName): FixtureBody {
  return JSON.parse(readFileSync(path.join(API_DIR, `${name}.json`), "utf8")) as FixtureBody;
}

/** Route the report's endpoints to its fixture, then open the report screen. */
export async function openReport(page: Page, name: FixtureName): Promise<FixtureBody> {
  const body = loadFixture(name);
  const id = body.report.id;
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const rest = url.pathname.replace(/^\/api/, "");
    const json = (status: number, payload: unknown) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(payload) });
    if (rest === `/reports/${id}`) return json(200, body.report);
    if (rest === `/reports/${id}/commentary`) {
      return body.commentary
        ? json(200, body.commentary)
        : json(404, { detail: { code: "commentary_not_found", message: "no commentary for this report yet" } });
    }
    if (rest === `/reports/${id}/review`) return json(200, body.review);
    if (rest === `/reports/${id}/original`) {
      const file = originalPdf(name);
      return file
        ? route.fulfill({ status: 200, contentType: "application/pdf", path: file })
        : json(404, { detail: { code: "original_not_found", message: "no PDF for this fixture" } });
    }
    return json(404, { detail: { code: "report_not_found", message: `unexpected ${rest}` } });
  });
  await page.goto(`/reports/${id}`);
  await expect(page.getByTestId("report-header")).toBeVisible();
  return body;
}

export const test = base;
export { expect };
