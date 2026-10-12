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
  | "example_stale"
  | "company_b";

interface FixtureBody {
  fixture: { id: number; name: string; states: string[] };
  report: { id: number };
  commentary: unknown | null;
  review: unknown;
  reported?: unknown;
}

export function loadFixture(name: FixtureName): FixtureBody {
  return JSON.parse(readFileSync(path.join(API_DIR, `${name}.json`), "utf8")) as FixtureBody;
}

/** A report-list row for a fixture, as GET /reports would give it (no figures). */
function summary(body: FixtureBody, index: number) {
  const r = body.report as {
    id: number; filename: string; document_type: string; status: string; page_count: number;
    pack?: { company_name?: string | null; periods?: { label?: string }[]; currency?: string; unit_scale?: number } | null;
    stale?: boolean;
  };
  const review = (body.review as { items?: { status: string }[] } | null)?.items ?? [];
  return {
    id: r.id, filename: r.filename, company_name: r.pack?.company_name ?? null, document_type: r.document_type,
    status: r.status, page_count: r.page_count, created_at: new Date(Date.UTC(2026, 9, 1, 12, 0) - index * 3_600_000).toISOString(),
    period_label: r.pack?.periods?.[0]?.label ?? null, currency: r.pack?.currency ?? null,
    unit_scale: r.pack?.unit_scale ?? null, open_review_items: review.filter((i) => i.status === "open").length,
    stale: Boolean(r.stale),
  };
}

/**
 * Answer /api/* from fixtures: each named report's endpoints, and GET /reports listing them all
 * (newest first, in the order given). Anything else is a 404, so an unexpected call is visible.
 */
export async function routeFixtures(page: Page, names: FixtureName[]): Promise<FixtureBody[]> {
  const bodies = names.map(loadFixture);
  const byId = new Map(bodies.map((b, i) => [String(b.report.id), { body: b, name: names[i]! }]));
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const rest = url.pathname.replace(/^\/api/, "");
    const json = (status: number, payload: unknown) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(payload) });
    if (rest === "/reports") return json(200, bodies.map(summary));
    const m = /^\/reports\/(\d+)(\/.*)?$/.exec(rest);
    const hit = m ? byId.get(m[1]!) : undefined;
    if (!hit) return json(404, { detail: { code: "report_not_found", message: `unexpected ${rest}` } });
    const { body, name } = hit;
    const tail = m![2] ?? "";
    if (tail === "") return json(200, body.report);
    if (tail === "/commentary") {
      return body.commentary
        ? json(200, body.commentary)
        : json(404, { detail: { code: "commentary_not_found", message: "no commentary for this report yet" } });
    }
    if (tail === "/review") return json(200, body.review);
    if (tail === "/reported-metrics") return json(200, body.reported ?? { metrics: [], notes: [] });
    if (tail === "/original") {
      const file = originalPdf(name);
      return file
        ? route.fulfill({ status: 200, contentType: "application/pdf", path: file })
        : json(404, { detail: { code: "original_not_found", message: "no PDF for this fixture" } });
    }
    return json(404, { detail: { code: "report_not_found", message: `unexpected ${rest}` } });
  });
  return bodies;
}

/**
 * Route the report's endpoints to its fixture, then open the report screen. `setup` registers a
 * test's own routes after the fixture's, so they take precedence (Playwright runs the most
 * recently registered matching route first).
 */
export async function openReport(
  page: Page,
  name: FixtureName,
  setup?: (page: Page) => Promise<void>,
): Promise<FixtureBody> {
  const [body] = await routeFixtures(page, [name]);
  await setup?.(page);
  await page.goto(`/reports/${body!.report.id}`);
  await expect(page.getByTestId("report-header")).toBeVisible();
  return body!;
}

/** The dashboard over a set of fixture reports. */
export async function openDashboard(page: Page, names: FixtureName[]): Promise<FixtureBody[]> {
  const bodies = await routeFixtures(page, names);
  await page.goto("/");
  await expect(page.getByTestId("dashboard")).toBeVisible();
  return bodies;
}

export const test = base;
export { expect };
