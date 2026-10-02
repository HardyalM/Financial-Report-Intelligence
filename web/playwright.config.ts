import { defineConfig, devices } from "@playwright/test";

// The specs live in tests/e2e at the repository root (docs/MILESTONES.md: allowed paths).
//
// Default: every /api/* response is served from tests/e2e/fixtures/api; no backend runs.
// E2E_LIVE=1: tests/e2e/live/*.spec.ts against the real API and worker
// (tests/e2e/live_server.py on a throwaway Postgres schema). Needs `docker compose up -d db`.
const live = Boolean(process.env.E2E_LIVE);
const port = Number(process.env.E2E_PORT ?? (live ? 3101 : 3100));
const apiPort = 8765;
const api = live ? `http://127.0.0.1:${apiPort}` : "http://127.0.0.1:9";
const distDir = live ? ".next-live" : ".next";
const next = process.env.E2E_DEV
  ? `npx next dev --port ${port}`
  : `npx next build && npx next start --port ${port}`;

export default defineConfig({
  testDir: "../tests/e2e",
  testMatch: live ? "live/**/*.spec.ts" : "**/*.spec.ts",
  testIgnore: live ? [] : ["live/**"],
  outputDir: live ? "./test-results-live" : "./test-results",
  fullyParallel: !live,
  workers: live ? 1 : undefined,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
    viewport: { width: 1440, height: 960 },
    locale: "en-GB",
    timezoneId: "Europe/London",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 960 } } }],
  webServer: [
    ...(live
      ? [
          {
            command: `uv run python -m tests.e2e.live_server --port ${apiPort}`,
            cwd: "..",
            url: `http://127.0.0.1:${apiPort}/healthz`,
            reuseExistingServer: false,
            timeout: 120_000,
            stdout: "pipe" as const,
            stderr: "pipe" as const,
          },
        ]
      : []),
    {
      command: next,
      url: `http://127.0.0.1:${port}`,
      reuseExistingServer: !process.env.CI && !live,
      timeout: 240_000,
      env: { FININTEL_API_URL: api, NEXT_DIST_DIR: distDir },
    },
  ],
});
