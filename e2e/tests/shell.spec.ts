import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("the API is healthy through the proxy", async ({ request }) => {
  const live = await request.get("/api/v1/healthz");
  expect(live.status()).toBe(200);
  expect(await live.json()).toEqual({ status: "ok" });
  expect(live.headers()["cache-control"]).toBe("no-store");
  expect(live.headers()["x-content-type-options"]).toBe("nosniff");

  const ready = await request.get("/api/v1/readyz");
  expect(await ready.json()).toEqual({ status: "ok", checks: { database: "ok", redis: "ok" } });
});

test("unknown API routes answer with problem details", async ({ request }) => {
  const response = await request.get("/api/v1/nope");
  expect(response.status()).toBe(404);
  expect(response.headers()["content-type"]).toBe("application/problem+json");
});

test("the chosen theme applies and survives a reload", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  await expect(page.locator("html")).not.toHaveClass(/dark/);
  await page.getByRole("button", { name: /Colour theme/ }).click();
  await page.getByRole("menuitemradio", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.reload();
  await expect(page.locator("html")).toHaveClass(/dark/);
});

test("keyboard users can skip to the content", async ({ page, isMobile }) => {
  test.skip(isMobile, "no hardware keyboard on the phone profile");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "My reviews" })).toBeVisible();
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();
  await expect(skip).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
});

test("on a phone the navigation opens as a sheet", async ({ page, isMobile }) => {
  test.skip(!isMobile, "phone layout only");
  await page.goto("/");
  await expect(page.getByRole("navigation", { name: "Workspace" })).toBeHidden();
  await page.getByRole("banner").getByRole("button", { name: "Toggle sidebar" }).click();
  const nav = page.getByRole("navigation", { name: "Workspace" });
  await expect(nav).toBeVisible();
  await nav.getByRole("link", { name: "My reviews" }).click();
  await expect(nav).toBeHidden();
});

for (const colorScheme of ["light", "dark"] as const) {
  test(`no serious accessibility violations (${colorScheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme });
    for (const path of ["/", "/missing-page"]) {
      await page.goto(path);
      await expect(page.getByRole("contentinfo")).toBeVisible();
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag22aa"])
        .analyze();
      const serious = results.violations.filter(
        (v) => v.impact === "serious" || v.impact === "critical",
      );
      expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
    }
  });
}
