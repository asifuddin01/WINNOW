import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { PASSWORD, createProject, createSignedInUser } from "../support/api";
import { uniqueEmail } from "../support/mail";

/** The same three papers as PubMed and as Scopus would give them, plus one that is not. */
function pubmed(): string {
  return [
    entry("Rotating night shifts and sleep quality in hospital nurses", "10.1111/jan.13894", 2019),
    entry(
      "Napping strategies during night shifts: a randomised trial",
      "10.1016/j.sleep.201",
      2020,
    ),
    entry("Melatonin for shift work sleep disorder: a meta-analysis", "10.1002/cochrane.55", 2021),
    entry("A study that only PubMed has", "10.1000/only.pubmed", 2018),
  ].join("\n");
}

function scopus(): string {
  return [
    // Same records, as another database writes them: shouting titles, short authors,
    // abbreviated journals, and in one case no DOI at all.
    entry("ROTATING NIGHT SHIFTS AND SLEEP QUALITY IN HOSPITAL NURSES.", "10.1111/jan.13894", 2019),
    // Scopus has it under the fuller title and without the DOI: alike, but not so alike
    // that Winnow should merge it without being asked.
    entry("Napping strategies during night shifts: a randomised crossover trial", null, 2020),
    entry("Melatonin for shift work sleep disorder: a meta-analysis", "10.1002/cochrane.55", 2021),
  ].join("\n");
}

function entry(title: string, doi: string | null, year: number): string {
  return [
    "TY  - JOUR",
    `TI  - ${title}`,
    "AU  - Smith, Jane A",
    `PY  - ${year}`,
    "JO  - Journal of Advanced Nursing",
    ...(doi ? [`DO  - ${doi}`] : []),
    "AB  - Whether rotating night shifts affect sleep quality in hospital staff.",
    "ER  - ",
  ].join("\n");
}

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "My reviews" })).toBeVisible();
}

/** Follow the review's own navigation; on a phone it sits behind the sheet. */
async function goTo(page: Page, name: string, isMobile: boolean) {
  if (isMobile) {
    await page.getByRole("banner").getByRole("button", { name: "Toggle sidebar" }).click();
  }
  await page.getByRole("navigation", { name: "This review" }).getByRole("link", { name }).click();
}

/**
 * Phase 4 acceptance: the same work imported from two databases is found, the certain
 * ones are merged without being asked, and the rest are decided side by side.
 */
test("duplicates from two databases are found, compared and merged", async ({
  page,
  request,
  baseURL,
  isMobile,
}) => {
  test.setTimeout(180_000);
  const owner = uniqueEmail("dedup");
  await createSignedInUser(request, baseURL ?? "", owner, "Ada Lovelace");
  const pid = await createProject(request, baseURL ?? "", `Duplicates ${Date.now().toString(36)}`);
  await signIn(page, owner);

  await page.goto(`/p/${pid}/import`);
  await page.getByLabel("Search export files").setInputFiles([
    {
      name: "pubmed_export.ris",
      mimeType: "application/x-research-info-systems",
      buffer: Buffer.from(pubmed(), "utf8"),
    },
    {
      name: "scopus_export.ris",
      mimeType: "application/x-research-info-systems",
      buffer: Buffer.from(scopus(), "utf8"),
    },
  ]);
  await page.getByRole("button", { name: /Upload and preview 2 files/ }).click();
  await page.getByRole("button", { name: "Import all 2 files" }).click();
  await expect(page.getByText("Imported", { exact: true })).toHaveCount(2, { timeout: 60_000 });

  // Deduplication runs on its own once an import lands (guide 8.4).
  await goTo(page, "Duplicates", isMobile);
  await expect(page).toHaveURL(new RegExp(`/p/${pid}/duplicates$`));

  // The two that share a DOI are merged already; the one without a DOI is for a person.
  const merged = page.getByText("Merged").locator("xpath=following-sibling::dd");
  await expect(merged).toHaveText("2", { timeout: 30_000 });

  const cluster = page.getByRole("article").first();
  await expect(cluster).toBeVisible();
  await expect(cluster.getByText(/alike/)).toBeVisible();
  await expect(cluster.getByRole("cell", { name: /Napping strategies/ }).first()).toBeVisible();

  // Winnow suggests the fuller copy — the one that still has its DOI.
  await expect(cluster.getByText("Winnow suggests it")).toBeVisible();
  await cluster.getByRole("button", { name: "Merge, keeping the chosen copy" }).click();
  await expect(page.getByText("Merged.")).toBeVisible();
  await expect(merged).toHaveText("3");

  // Three duplicates gone: seven records came in, four are left to screen.
  await goTo(page, "Records", isMobile);
  await expect(page.getByText("4 records")).toBeVisible();

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag22aa"])
    .analyze();
  const serious = results.violations.filter(
    (violation) => violation.impact === "serious" || violation.impact === "critical",
  );
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
});
