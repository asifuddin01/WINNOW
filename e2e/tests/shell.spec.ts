import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { SIGNED_IN_STATE } from "../global-setup";

async function expectNoSeriousViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag22aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical",
  );
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
}

test("the API is healthy through the proxy", async ({ request }) => {
  const live = await request.get("/api/v1/healthz");
  expect(live.status()).toBe(200);
  expect(await live.json()).toEqual({ status: "ok" });
  expect(live.headers()["cache-control"]).toBe("no-store");

  const ready = await request.get("/api/v1/readyz");
  expect(await ready.json()).toEqual({ status: "ok", checks: { database: "ok", redis: "ok" } });
});

test("security headers (guide 12.5)", async ({ request }) => {
  const page = await request.get("/login");
  const csp = page.headers()["content-security-policy"] ?? "";
  for (const directive of [
    "default-src 'self'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "connect-src 'self'",
  ]) {
    expect(csp).toContain(directive);
  }
  expect(page.headers()["x-content-type-options"]).toBe("nosniff");
  expect(page.headers()["referrer-policy"]).toBe("strict-origin-when-cross-origin");
  expect(page.headers()["permissions-policy"]).toContain("camera=()");
  expect(page.headers()["cross-origin-opener-policy"]).toBe("same-origin");
  expect(page.headers()["server"]).toBeUndefined();

  const api = await request.get("/api/v1/healthz");
  expect(api.headers()["content-security-policy"]).toBe(
    "default-src 'none'; frame-ancestors 'none'",
  );
});

test("writes without a CSRF token are refused", async ({ request, baseURL }) => {
  const response = await request.post("/api/v1/auth/login", {
    data: { email: "someone@example.com", password: "whatever it is" },
    headers: { Origin: baseURL ?? "" },
  });
  expect(response.status()).toBe(403);
  expect((await response.json()).code).toBe("csrf_invalid");
});

test("unknown API routes answer with problem details", async ({ request }) => {
  const response = await request.get("/api/v1/nope");
  expect(response.status()).toBe(404);
  expect(response.headers()["content-type"]).toBe("application/problem+json");
});

test("signed-out visitors are sent to sign in", async ({ page }) => {
  await page.goto("/account");
  await expect(page).toHaveURL(/\/login\?redirect=%2Faccount/);
  await expect(page.getByRole("heading", { name: "Sign in to Winnow" })).toBeVisible();
});

for (const colorScheme of ["light", "dark"] as const) {
  test(`sign-in pages have no serious accessibility violations (${colorScheme})`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme });
    for (const path of ["/login", "/register", "/forgot", "/missing-page"]) {
      await page.goto(path);
      await expect(page.getByRole("contentinfo")).toBeVisible();
      await expectNoSeriousViolations(page);
    }
  });
}

test.describe("signed in", () => {
  test.use({ storageState: SIGNED_IN_STATE });

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

  test("the command palette jumps anywhere from the keyboard (guide 11.2)", async ({
    page,
    isMobile,
  }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "My reviews" })).toBeVisible();
    if (isMobile) {
      await page.getByRole("button", { name: /Search or jump to/ }).click();
    } else {
      await page.keyboard.press("ControlOrMeta+k");
    }
    const input = page.getByRole("combobox", { name: /Search pages, reviews, records/ });
    await expect(input).toBeFocused();
    await expectNoSeriousViolations(page);
    await input.fill("account");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/account$/);
    await expect(input).toBeHidden();
  });

  test("keyboard users can skip to the content", async ({ page, isMobile }) => {
    test.skip(isMobile, "no hardware keyboard on the phone profile");
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "My reviews" })).toBeVisible();
    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: "Skip to content" });
    await expect(skip).toBeFocused();
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
    test(`app pages have no serious accessibility violations (${colorScheme})`, async ({
      page,
    }) => {
      await page.emulateMedia({ colorScheme });
      for (const path of ["/", "/account"]) {
        await page.goto(path);
        await expect(page.getByRole("contentinfo")).toBeVisible();
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await expectNoSeriousViolations(page);
      }
    });
  }
});
