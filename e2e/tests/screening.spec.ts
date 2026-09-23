import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { addMember, createProject, createSignedInUser, importRis } from "../support/api";
import { uniqueEmail } from "../support/mail";

const RECORDS = {
  agree: "Night shift work and sleep in intensive care nurses",
  disagree: "Melatonin for jet lag in airline pilots",
  out: "A survey of hospital car parking",
};

function ris(): string {
  return Object.values(RECORDS)
    .map((title, index) =>
      [
        "TY  - JOUR",
        `TI  - ${title}`,
        "AU  - Smith, Jane A",
        `PY  - ${2018 + index}`,
        "JO  - Sleep Medicine",
        `DO  - 10.1000/screen.${index}`,
        `AB  - An abstract about ${title.toLowerCase()}.`,
        "ER  - ",
      ].join("\n"),
    )
    .join("\n");
}

/** Screen every record on the page, choosing by title; returns the titles seen. */
async function screenAll(
  page: Page,
  choose: (title: string) => "include" | "exclude" | "maybe",
  how: "keys" | "buttons",
): Promise<string[]> {
  const seen: string[] = [];
  for (let step = 0; step < 3; step++) {
    const heading = page.getByRole("main").getByRole("heading", { level: 2 }).first();
    await expect(heading).toBeVisible();
    const title = (await heading.textContent()) ?? "";
    seen.push(title);
    const decision = choose(title);
    if (how === "keys") {
      await page.keyboard.press({ include: "i", exclude: "e", maybe: "m" }[decision]);
    } else {
      await page
        .getByRole("group", { name: "Decision" })
        .getByRole("button", { name: new RegExp(`^${decision}`, "i") })
        .click();
    }
    // The next record is already there: no loading state in between (guide 2.2).
    if (step < 2) await expect(heading).not.toHaveText(title, { timeout: 2_000 });
  }
  await expect(page.getByText("Nothing left for you to screen here.")).toBeVisible();
  return seen;
}

/**
 * Phase 5 acceptance: two reviewers screen the same records, blind to each other; where
 * they disagree it becomes a conflict that only a resolver sees, and it is resolved.
 * The second reviewer works on a 360-pixel phone screen, with the on-screen buttons.
 */
test("two reviewers screen blind, and their disagreement is resolved", async ({
  browser,
  baseURL,
}) => {
  test.setTimeout(180_000);
  const url = baseURL ?? "";
  const ownerContext = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const reviewerContext = await browser.newContext({
    viewport: { width: 360, height: 740 },
    hasTouch: true,
  });
  const owner = await ownerContext.newPage();
  const reviewer = await reviewerContext.newPage();

  await createSignedInUser(ownerContext.request, url, uniqueEmail("screen-owner"), "Ada Lovelace");
  const reviewerEmail = uniqueEmail("screen-reviewer");
  await createSignedInUser(reviewerContext.request, url, reviewerEmail, "Grace Hopper");
  const pid = await createProject(
    ownerContext.request,
    url,
    `Screening ${Date.now().toString(36)}`,
  );
  await addMember(ownerContext.request, reviewerContext.request, url, pid, reviewerEmail);
  await importRis(ownerContext.request, url, pid, ris());

  // The reviewer, on a small phone, taps the buttons.
  await reviewer.goto(`/p/${pid}/screen/ta`);
  await expect(reviewer.getByText("0 / 3 screened by you")).toBeVisible();
  const width = await reviewer.evaluate(() => document.documentElement.scrollWidth);
  expect(width).toBeLessThanOrEqual(360);
  await screenAll(
    reviewer,
    (title) => (title.includes("parking") ? "exclude" : "include"),
    "buttons",
  );

  // The owner, on a desktop, uses the keyboard, and stays blind while screening.
  await owner.goto(`/p/${pid}/screen/ta`);
  await expect(owner.getByText("0 / 3 screened by you")).toBeVisible();
  await expect(owner.getByRole("region", { name: "Other reviewers" })).toHaveCount(0);
  await screenAll(
    owner,
    (title) => (title.includes("Night shift") ? "include" : "exclude"),
    "keys",
  );

  // The reviewer learns nothing of the owner's decisions, not even that they differ:
  // the records list shows their own decision, and there is no conflicts page for them.
  await reviewer.goto(`/p/${pid}/records`);
  const disagreed = reviewer.getByRole("button", { name: new RegExp(RECORDS.disagree) });
  await expect(disagreed).toContainText("Included");
  await expect(reviewer.getByText("Conflict", { exact: true })).toHaveCount(0);
  await reviewer.goto(`/p/${pid}/conflicts`);
  await expect(reviewer.getByText(/for the review's owners and admins/)).toBeVisible();

  // The owner resolves it; on the conflicts page, and only there, both decisions show.
  await owner.goto(`/p/${pid}/conflicts`);
  const card = owner.getByRole("article");
  await expect(card).toHaveCount(1);
  await expect(card.getByRole("heading", { name: RECORDS.disagree })).toBeVisible();
  await expect(card.getByText("Grace Hopper: Included")).toBeVisible();
  await expect(card.getByText("Ada Lovelace: Excluded")).toBeVisible();
  await card.getByRole("button", { name: "Wrong population" }).click();
  await card.getByLabel(/Why/).fill("Pilots, not nurses.");
  await card.getByRole("button", { name: "Exclude" }).click();
  await expect(owner.getByText("No conflicts.")).toBeVisible();

  const results = await new AxeBuilder({ page: reviewer })
    .withTags(["wcag2a", "wcag2aa", "wcag22aa"])
    .analyze();
  const serious = results.violations.filter(
    (violation) => violation.impact === "serious" || violation.impact === "critical",
  );
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);

  await ownerContext.close();
  await reviewerContext.close();
});

test("the screening page has no serious accessibility problems", async ({ browser, baseURL }) => {
  // A sign-up, a review, an import and two full axe runs: more than the default allows.
  test.setTimeout(90_000);
  const url = baseURL ?? "";
  const context = await browser.newContext();
  const page = await context.newPage();
  await createSignedInUser(context.request, url, uniqueEmail("screen-a11y"), "Hedy Lamarr");
  const pid = await createProject(context.request, url, `Screen a11y ${Date.now().toString(36)}`);
  await importRis(context.request, url, pid, ris());
  for (const colorScheme of ["light", "dark"] as const) {
    // Chosen before the page loads: switching on a loaded page would have axe measure
    // colours halfway through their transition.
    await page.emulateMedia({ colorScheme });
    await page.goto(`/p/${pid}/screen/ta`);
    await expect(page.getByRole("group", { name: "Decision" })).toBeVisible();
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag22aa"])
      .analyze();
    const serious = results.violations.filter(
      (violation) => violation.impact === "serious" || violation.impact === "critical",
    );
    expect(serious, `${colorScheme}: ${JSON.stringify(serious, null, 2)}`).toEqual([]);
  }
  await context.close();
});
