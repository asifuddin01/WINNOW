import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against the running stack (`make up`), through Caddy exactly as a
 * browser reaches it, with Mailpit catching the emails. Chromium on desktop and phone
 * viewports; Firefox and WebKit join when the full review journey exists (guide 15).
 */
export default defineConfig({
  testDir: "./tests",
  globalSetup: "./global-setup.ts",
  fullyParallel: true,
  // Two browsers at a time: the stack itself runs in Docker on the same machine.
  workers: 2,
  forbidOnly: Boolean(process.env.CI),
  // The development stack compiles route chunks on demand, so first visits are slow.
  expect: { timeout: 10_000 },
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
