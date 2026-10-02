import { defineConfig, devices } from "@playwright/test";

// The specs live in tests/e2e at the repository root (docs/MILESTONES.md: allowed paths).
// Every API response is served from tests/e2e/fixtures/api, so no backend runs.
const port = Number(process.env.E2E_PORT ?? 3100);

export default defineConfig({
  testDir: "../tests/e2e",
  testMatch: "**/*.spec.ts",
  outputDir: "./test-results",
  fullyParallel: true,
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
  webServer: {
    command: process.env.E2E_DEV ? `npx next dev --port ${port}` : `npx next build && npx next start --port ${port}`,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: { FININTEL_API_URL: "http://127.0.0.1:9" },
  },
});
