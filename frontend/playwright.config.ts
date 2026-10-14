import { defineConfig, devices } from "@playwright/test";
import { browserPort, E2E_HOST } from "./e2e/ports.mjs";

// Deterministic mock-smoke suite for the Svelte webapp. It drives the
// docs-demo build (mockApi, no backend/network), so it is the standing UI
// regression gate for the runes migration: boot, every nav switch, webapp
// dialogs, core admin sections, admin dialogs, dialog tabs, disclosure panels,
// activation handoff, and zero console errors.
//
// The webServer rebuilds the demo runtime from the current source before
// serving it, so the suite always exercises the latest code. Set
// PLAYWRIGHT_SKIP_DEMO_BUILD=1 to serve an existing build (faster local loop).

const PORT = browserPort(process.env.PORT);
const baseURL = `http://${E2E_HOST}:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  // Port-policy unit tests run in Vitest, not in the browser suite.
  testIgnore: ["**/ports.test.mjs"],
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  timeout: 120_000,
  workers: process.env.PLAYWRIGHT_WORKERS
    ? Number(process.env.PLAYWRIGHT_WORKERS)
    : process.env.CI
      ? 1
      : 2,
  reporter: process.env.CI ? [["html", { open: "never" }], ["list"]] : "list",
  use: {
    baseURL,
    browserName: "chromium",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "node ./e2e/serve-demo.mjs",
    url: `${baseURL}/demo/runtime/app/`,
    reuseExistingServer: false,
    timeout: 300_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
