import { execSync } from "node:child_process";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { createSignedInUser } from "../support/api";
import { uniqueEmail } from "../support/mail";

async function noSeriousA11yProblems(page: Page, where: string): Promise<void> {
  // A toast fading in is measured half transparent; check the page once it has settled.
  await expect
    .poll(() =>
      page
        .locator("[data-sonner-toast]")
        .evaluateAll((toasts) => toasts.every((toast) => getComputedStyle(toast).opacity === "1")),
    )
    .toBe(true);
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag22aa"])
    .analyze();
  const serious = results.violations.filter(
    (violation) => violation.impact === "serious" || violation.impact === "critical",
  );
  expect(serious, `${where}: ${JSON.stringify(serious, null, 2)}`).toEqual([]);
}

async function shot(page: Page, name: string): Promise<void> {
  const folder = process.env.SCREENS;
  if (folder) await page.screenshot({ path: `${folder}/${name}.png`, fullPage: true });
}

/** Guide 8.18: an instance administrator disables and enables an account, changes the
 * registration mode while Winnow runs, and reads its health. */
test("the instance admin panel", async ({ browser, baseURL }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "one journey is enough");
  test.setTimeout(180_000);
  const url = baseURL ?? "";
  const adminContext = await browser.newContext();
  const other = await browser.newContext();
  const adminEmail = uniqueEmail("admin");
  const otherEmail = uniqueEmail("admin-target");
  await createSignedInUser(adminContext.request, url, adminEmail, "Ngozi Okafor");
  await createSignedInUser(other.request, url, otherEmail, "Elin Lindqvist");
  // A fixture account made an administrator; the suite's cleanup demotes it afterwards.
  execSync(
    `docker compose exec -T db psql -U winnow -d winnow -c "update users set is_instance_admin = true where email = '${adminEmail}'"`,
    { stdio: "ignore", cwd: ".." },
  );

  const page = await adminContext.newPage();
  await page.goto("/");
  await page.getByRole("link", { name: "Instance admin" }).click();
  await expect(page.getByRole("heading", { name: "Instance admin", level: 1 })).toBeVisible();
  await page.getByLabel("Find someone").fill(otherEmail);
  const row = page.getByRole("row", { name: new RegExp(otherEmail) });
  await expect(row).toBeVisible();
  await noSeriousA11yProblems(page, "People");
  await shot(page, "admin-people");

  await row.getByRole("button", { name: /Actions for/ }).click();
  await page.getByRole("menuitem", { name: "Disable" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Disable" }).click();
  await expect(row.getByText("Disabled")).toBeVisible();
  expect((await other.request.get("/api/v1/auth/me")).status()).toBe(401);

  await row.getByRole("button", { name: /Actions for/ }).click();
  await page.getByRole("menuitem", { name: "Enable" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Enable" }).click();
  await expect(row.getByText("Disabled")).toHaveCount(0);

  // Registration closes at once, without a restart, and opens again.
  await page.getByRole("link", { name: "Settings" }).click();
  await page.getByLabel("Who can create an account").click();
  await page.getByRole("option", { name: /^By invitation/ }).click();
  await expect(page.getByText("Set here")).toBeVisible();
  const options = await (await other.request.get("/api/v1/auth/options")).json();
  expect(options.registration).toBe("invite_only");
  await noSeriousA11yProblems(page, "Settings");
  await shot(page, "admin-settings");
  await page.getByRole("button", { name: "Use the value in .env instead" }).click();
  await expect(page.getByRole("button", { name: "Use the value in .env instead" })).toHaveCount(0);

  await page.getByRole("link", { name: "Health" }).click();
  await expect(page.getByRole("region", { name: "Worker" })).toContainText("Running");
  await noSeriousA11yProblems(page, "Health");
  await shot(page, "admin-health");

  await adminContext.close();
  await other.close();
});
