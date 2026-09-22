import { expect, test, type Page } from "@playwright/test";

import { SIGNED_IN_STATE } from "../global-setup";

/** Guide 19.2: "Built by Asif" linking to https://asifuddin.com on every page. */
async function expectFooter(page: Page) {
  const footer = page.getByRole("contentinfo");
  await expect(footer).toContainText("Winnow · Built by Asif");
  const link = footer.getByRole("link", { name: "Asif" });
  await expect(link).toHaveAttribute("href", "https://asifuddin.com");
  await expect(link).toHaveAttribute("target", "_blank");
  await expect(link).toHaveAttribute("rel", /noopener/);
  await expect(link).toHaveAttribute("rel", /noreferrer/);
}

test.describe("signed out", () => {
  for (const [path, heading] of [
    ["/login", "Sign in to Winnow"],
    ["/register", "Create your account"],
    ["/forgot", "Reset your password"],
    ["/this/page/does/not/exist", "Page not found"],
  ] as const) {
    test(`${path} shows the footer`, async ({ page }) => {
      await page.goto(path);
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
      await expectFooter(page);
    });
  }
});

test.describe("signed in", () => {
  test.use({ storageState: SIGNED_IN_STATE });

  test("the dashboard shows the footer, below the content", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: "My reviews" })).toBeVisible();
    await expectFooter(page);
    const position = await page
      .getByRole("contentinfo")
      .evaluate((footer) => getComputedStyle(footer).position);
    expect(position).toBe("static");
  });

  test("the account page shows the footer", async ({ page }) => {
    await page.goto("/account");
    await expect(page.getByRole("heading", { name: "Account and security" })).toBeVisible();
    await expectFooter(page);
  });
});
