import { expect, test, type Page } from "@playwright/test";

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

test("dashboard shows the footer", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "My reviews" })).toBeVisible();
  await expectFooter(page);
});

test("not-found page shows the footer", async ({ page }) => {
  await page.goto("/this/page/does/not/exist");
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
  await expectFooter(page);
});

test("the footer sits below the content, never over it", async ({ page }) => {
  await page.goto("/");
  const position = await page
    .getByRole("contentinfo")
    .evaluate((footer) => getComputedStyle(footer).position);
  expect(position).toBe("static");
});
