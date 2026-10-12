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

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

/**
 * A dashboard card for a fixture, by the same rules as the server (finintel/api/dashboard.py, whose
 * own tests check it against the real pipeline): counts and the ratio engine's values, nothing new.
 */
function card(body: FixtureBody, index: number, sample: boolean) {
  const r = body.report as Json;
  const pack = r.pack as Json | null;
  const periods = (pack?.periods ?? []) as Json[];
  const current = periods[0]?.id;
  let figures: Json | null = null;
  if (pack && current) {
    figures = { read: 0, derived: 0, manual: 0, empty: 0 };
    for (const item of Object.values(pack.items as Json)) {
      const v = (item.values as Json[]).find((x) => x.period_id === current);
      if (!v) continue;
      const engine = String(v.engine ?? "");
      if (v.value == null) figures.empty++;
      else if (engine.startsWith("human_override")) figures.manual++;
      else if (engine === "derived") figures.derived++;
      else figures.read++;
    }
  }
  const docType = r.document_type !== "other" || !pack ? r.document_type : (pack.document_type ?? r.document_type);
  const ratioPeriod = (r.ratios?.periods ?? [])[0] as Json | undefined;
  const change = ((r.ratios?.changes ?? []) as Json[]).find((c) => c.to_period_id === ratioPeriod?.period_id);
  const order = docType === "bank"
    ? ["cost_to_income", "loan_to_deposit", "operating_margin", "roce", "current_ratio", "debt_to_equity"]
    : ["operating_margin", "roce", "current_ratio", "debt_to_equity", "cost_to_income", "loan_to_deposit"];
  const ratios = order
    .map((name) => ({ name, r: ratioPeriod?.ratios?.[name] as Json | undefined }))
    .filter(({ r: x }) => x && x.status !== "not_applicable")
    .map(({ name, r: x }) => ({
      name, label: x!.label ?? name, value: x!.value ?? null, unit: x!.unit ?? "fraction", status: x!.status ?? "",
      flags: x!.flags ?? [], change_kind: change?.ratios?.[name]?.kind ?? null, change: change?.ratios?.[name]?.value ?? null,
    }));
  const out = (body.commentary as Json | null)?.output as Json | undefined;
  const paragraphs = ((out?.topics ?? []) as Json[]).flatMap((t) => t.paragraphs ?? []);
  const bullets = (out?.executive_summary?.bullets ?? []) as Json[];
  const review = ((body.review as Json | null)?.items ?? []) as Json[];
  const open = review.filter((i) => i.status === "open").length;
  const waiting = r.status === "needs_unit_confirmation" ? "unit" : r.status === "needs_document_type" ? "document_type"
    : r.status === "failed" ? "failed" : open ? "review" : null;
  return {
    id: r.id, title: pack?.company_name ?? String(r.filename).replace(/\.pdf$/i, ""), filename: r.filename,
    document_type: docType, status: r.status, is_sample: sample,
    created_at: new Date(Date.UTC(2026, 9, 1, 12, 0) - index * 3_600_000).toISOString(), page_count: r.page_count,
    period_label: periods[0]?.label ?? null, prior_label: periods[1]?.label ?? null,
    currency: pack?.currency ?? null, unit_scale: pack?.unit_scale ?? null, figures, ratios,
    commentary: out ? {
      mode: out.mode, topics_ok: ((out.topics ?? []) as Json[]).filter((t) => t.status === "ok").length,
      topics: (out.topics ?? []).length,
      citations: [...paragraphs, ...bullets].reduce((n: number, p: Json) => n + (p.citations?.length ?? 0), 0),
      stale: Boolean((body.commentary as Json).stale),
    } : null,
    open_review_items: open, waiting_for: waiting, jobs: r.jobs ?? [],
  };
}

/**
 * Answer /api/* from fixtures: each named report's endpoints, and GET /reports listing them all
 * (newest first, in the order given). Anything else is a 404, so an unexpected call is visible.
 */
export async function routeFixtures(
  page: Page,
  names: FixtureName[],
  opts: { samples?: FixtureName[] } = {},
): Promise<FixtureBody[]> {
  const bodies = names.map(loadFixture);
  const samples = new Set(opts.samples ?? []);
  const byId = new Map(bodies.map((b, i) => [String(b.report.id), { body: b, name: names[i]! }]));
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const rest = url.pathname.replace(/^\/api/, "");
    const json = (status: number, payload: unknown) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(payload) });
    if (rest === "/reports") {
      return json(200, bodies.map((b, i) => ({ ...summary(b, i), is_sample: samples.has(names[i]!) })));
    }
    if (rest === "/dashboard") {
      const cards = bodies.map((b, i) => card(b, i, samples.has(names[i]!)));
      return json(200, { reports: cards, has_samples: cards.some((c) => c.is_sample) });
    }
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

/** The dashboard over a set of fixture reports (some optionally marked as samples). */
export async function openDashboard(
  page: Page,
  names: FixtureName[],
  opts: { samples?: FixtureName[] } = {},
): Promise<FixtureBody[]> {
  const bodies = await routeFixtures(page, names, opts);
  await page.goto("/");
  await expect(page.getByTestId("dashboard")).toBeVisible();
  return bodies;
}

export const test = base;
export { expect };
