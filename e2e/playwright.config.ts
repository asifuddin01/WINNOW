import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against the running stack (`make up`), through Caddy exactly as a
 * browser reaches it. Phase 0 runs Chromium on desktop and phone viewports; Firefox
 * and WebKit join when the full user journey exists (guide 15).
 */
export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:8080",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
});
