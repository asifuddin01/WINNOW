import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { PASSWORD, createSignedInUser } from "../support/api";
import { emailedLink, uniqueEmail } from "../support/mail";

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "My reviews" })).toBeVisible();
}

/**
 * Phase 2 acceptance: two people work on one review with the right permissions — a
 * review is created in the wizard, someone is invited by email, joins from the link, is
 * kept out of the setup until promoted, and then let in.
 */
test("two people set up and share a review", async ({ page, request, browser, baseURL }) => {
  test.setTimeout(180_000); // two accounts, three emails through the worker
  const owner = uniqueEmail("owner");
  const reviewer = uniqueEmail("reviewer");
  const title = `Shift work and sleep ${Date.now().toString(36)}`;

  await createSignedInUser(request, baseURL ?? "", owner, "Ada Lovelace");
  await signIn(page, owner);

  // Step one of the wizard.
  await page.getByRole("link", { name: "New review" }).first().click();
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page
    .getByLabel("Research question")
    .fill("Do night shifts affect sleep quality in nurses?");
  await page.getByRole("button", { name: "Continue" }).click();

  // Step two: criteria, keywords and the exclusion reasons that come as standard.
  await expect(page.getByRole("heading", { name: "What counts as relevant?" })).toBeVisible();
  await page.getByLabel("New inclusion criterion").fill("Adults working night shifts");
  await page.getByRole("button", { name: "Add inclusion criterion" }).click();
  await expect(page.getByText("Adults working night shifts")).toBeVisible();

  await page.getByLabel("New keyword group").fill("Population");
  await page.getByRole("button", { name: "Add group" }).click();
  await page.getByLabel("Terms for Population").fill("nurses, shift workers");
  await page.getByRole("button", { name: "Add to Population" }).click();
  await expect(page.getByText("shift workers")).toBeVisible();
  await expect(page.getByText("Wrong population", { exact: true })).toBeVisible();

  // Step three: invite the second person.
  await page.getByRole("button", { name: "Continue to the team" }).click();
  await page.getByLabel("Invite by email").fill(reviewer);
  await page.getByRole("button", { name: "Send invitation" }).click();
  await expect(page.getByText(reviewer).first()).toBeVisible();

  await page.getByRole("button", { name: "Finish and open the review" }).click();
  await expect(page.getByRole("heading", { name: title, level: 1 })).toBeVisible();
  const projectUrl = new URL(page.url()).pathname;

  // The second person follows the emailed link, makes an account and accepts.
  const second = await browser.newContext();
  const joiner = await second.newPage();
  await joiner.goto(await emailedLink(request, reviewer, "invite"));
  await expect(joiner.getByRole("heading", { name: "You are invited" })).toBeVisible();
  await expect(joiner.getByText(title)).toBeVisible();
  await joiner.getByRole("link", { name: "Create an account" }).click();
  await joiner.getByLabel("Name", { exact: true }).fill("Grace Hopper");
  await joiner.getByLabel("Email", { exact: true }).fill(reviewer);
  await joiner.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await joiner.getByRole("button", { name: "Create account" }).click();
  await expect(joiner.getByRole("heading", { name: "Check your email" })).toBeVisible();

  await joiner.goto(await emailedLink(request, reviewer, "verify"));
  await joiner.getByRole("button", { name: "Confirm email address" }).click();
  await expect(joiner.getByRole("heading", { name: "Email confirmed" })).toBeVisible();
  await signIn(joiner, reviewer);

  await joiner.goto(await emailedLink(request, reviewer, "invite"));
  await joiner.getByRole("button", { name: "Accept invitation" }).click();
  await expect(joiner.getByRole("heading", { name: title, level: 1 })).toBeVisible();
  await expect(joiner.getByText("Adults working night shifts")).toBeVisible();

  // A reviewer reads the setup but cannot change it.
  await joiner.goto(`${projectUrl}/settings/criteria`);
  await expect(joiner.getByText("Adults working night shifts")).toBeVisible();
  await expect(joiner.getByRole("button", { name: "Add inclusion criterion" })).toHaveCount(0);
  await joiner.goto(`${projectUrl}/settings/team`);
  await expect(joiner.getByLabel("Invite by email")).toHaveCount(0);

  // The owner promotes them, and now they can.
  await page.goto(`${projectUrl}/settings/team`);
  await expect(page.getByLabel("Role for Grace Hopper")).toBeVisible();
  await page.getByLabel("Role for Grace Hopper").click();
  await page.getByRole("option", { name: /Admin/ }).click();
  await expect(page.getByText("Role changed.")).toBeVisible();

  await joiner.goto(`${projectUrl}/settings/criteria`);
  await joiner.getByLabel("New exclusion criterion").fill("Animal studies");
  await joiner.getByRole("button", { name: "Add exclusion criterion" }).click();
  await expect(joiner.getByText("Animal studies")).toBeVisible();

  // And the owner sees their work.
  await page.goto(projectUrl);
  await expect(page.getByText("Animal studies")).toBeVisible();

  // Guide 14: nothing serious in the way of anyone using it.
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag22aa"])
    .analyze();
  const serious = results.violations.filter(
    (violation) => violation.impact === "serious" || violation.impact === "critical",
  );
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
  await second.close();
});

test("a review you are not on is not found", async ({ page, request, baseURL }) => {
  const outsider = uniqueEmail("outsider");
  await createSignedInUser(request, baseURL ?? "", outsider);
  await signIn(page, outsider);
  await page.goto("/p/0192f0c1-0000-7000-8000-000000000404");
  await expect(page.getByRole("heading", { name: "Review not found" })).toBeVisible();
});
