import { readFileSync } from "node:fs";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { addMember, apiSend, createProject, createSignedInUser, importRis } from "../support/api";
import { uniqueEmail } from "../support/mail";

const TITLES = [
  "Night shifts and sleep in nurses",
  "Rotating rosters and fatigue",
  "Melatonin for shift workers",
  "Circadian disruption in paramedics",
  "Caffeine and night-time alertness",
  "Light therapy on the ward",
];

function ris(): string {
  return TITLES.map((title, index) =>
    [
      "TY  - JOUR",
      `TI  - ${title}`,
      `AU  - ${["Okafor, Ngozi", "Lindqvist, Elin", "Tanaka, Hiro"][index % 3]}`,
      `PY  - ${2016 + index}`,
      "JO  - Sleep Medicine",
      `DO  - 10.1000/report.${index}`,
      "AB  - An abstract about sleep and shift work.",
      "ER  - ",
    ].join("\n"),
  ).join("\n");
}

/** Screenshots for the owner, when SCREENS names a folder; nothing otherwise. */
async function shot(page: Page, name: string): Promise<void> {
  const folder = process.env.SCREENS;
  if (!folder) return;
  await page.screenshot({ path: `${folder}/${name}.png`, fullPage: true });
  await page.emulateMedia({ colorScheme: "dark" });
  // Colours ease between themes; shoot once they have.
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${folder}/${name}-dark.png`, fullPage: true });
  await page.emulateMedia({ colorScheme: "light" });
}

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

async function decide(
  request: APIRequestContext,
  baseURL: string,
  pid: string,
  rid: string,
  decision: string,
  stage = "title_abstract",
): Promise<void> {
  await apiSend(request, baseURL, "PUT", `/api/v1/projects/${pid}/records/${rid}/decision`, {
    stage,
    decision,
  });
}

/**
 * Phase 8: the PRISMA flow, agreement, exports, the audit log and risk of bias, read and
 * used through the browser; then the review's backup restored as a new review.
 */
test("report, risk of bias, and a backup restored as a new review", async ({
  browser,
  baseURL,
}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "one journey is enough; pages are checked below");
  test.setTimeout(240_000);
  const url = baseURL ?? "";
  const owner = await browser.newContext();
  const reviewer = await browser.newContext();
  const ownerEmail = uniqueEmail("report-owner");
  const reviewerEmail = uniqueEmail("report-reviewer");
  await createSignedInUser(owner.request, url, ownerEmail, "Ngozi Okafor");
  await createSignedInUser(reviewer.request, url, reviewerEmail, "Elin Lindqvist");

  const pid = await createProject(owner.request, url, `Shift work ${Date.now().toString(36)}`);
  await apiSend(owner.request, url, "PATCH", `/api/v1/projects/${pid}`, {
    settings: { reviewers_per_record_ta: 2, reviewers_per_record_ft: 1 },
  });
  await apiSend(owner.request, url, "PATCH", `/api/v1/projects/${pid}/membership`, {
    keep_blind: false,
  });
  await addMember(owner.request, reviewer.request, url, pid, reviewerEmail);
  await importRis(owner.request, url, pid, ris());
  const records = (await (await owner.request.get(`/api/v1/projects/${pid}/records`)).json()) as {
    items: { id: string; title: string }[];
  };
  const id = (title: string) => records.items.find((r) => r.title === title)?.id ?? "";
  // Five agreements and one disagreement in six: kappa (5/6 - 1/2) / (1 - 1/2) = 0.67.
  const mine = ["include", "include", "include", "include", "exclude", "exclude"];
  const theirs = ["include", "include", "include", "exclude", "exclude", "exclude"];
  for (const [index, title] of TITLES.entries()) {
    await decide(owner.request, url, pid, id(title), mine[index]!);
    await decide(reviewer.request, url, pid, id(title), theirs[index]!);
  }
  await decide(owner.request, url, pid, id(TITLES[0]!), "include", "full_text");
  await decide(owner.request, url, pid, id(TITLES[1]!), "include", "full_text");

  const page = await owner.newPage();

  // PRISMA: the diagram, its numbers, and what Winnow cannot count.
  await page.goto(`/p/${pid}/report`);
  await expect(page.getByRole("heading", { name: "Report", level: 1 })).toBeVisible();
  const diagram = page.getByRole("img", { name: /PRISMA 2020 flow diagram/ });
  await expect(diagram).toBeVisible();
  await expect.poll(() => diagram.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
  await expect(page.getByText(/Screening is not finished/)).toBeVisible();
  await page.getByText("The numbers in the diagram").click();
  await expect(page.getByRole("row", { name: "Records screened 6" })).toBeVisible();
  await expect(page.getByRole("row", { name: "Studies included in review 2" })).toBeVisible();
  await page.getByRole("button", { name: "Add a source" }).click();
  await page.getByRole("textbox", { name: "Source 1", exact: true }).fill("Citation searching");
  await page.getByRole("textbox", { name: "Records", exact: true }).fill("3");
  await page.getByRole("button", { name: "Save counts" }).click();
  await expect(page.getByText("Saved. The diagram is up to date.")).toBeVisible();
  await expect(
    page.getByRole("row", { name: "Records from Citation searching (other sources) 3" }),
  ).toBeVisible();
  await noSeriousA11yProblems(page, "PRISMA");
  await shot(page, "report-prisma");

  // Statistics: progress and agreement.
  await page.getByRole("link", { name: "Statistics" }).click();
  const agreement = page.getByRole("table", { name: /Title and abstract: agreement/ });
  await expect(agreement.getByRole("row", { name: /Ngozi Okafor and Elin Lindqvist|Elin Lindqvist and Ngozi Okafor/ })).toContainText("0.67");
  await expect(agreement).toContainText(/substantial/i);
  await noSeriousA11yProblems(page, "Statistics");
  await shot(page, "report-stats");

  // Exports: a CSV of the included records, made in the worker, then downloaded.
  await page.getByRole("link", { name: "Exports" }).click();
  await page.getByRole("button", { name: "Make the file" }).click();
  const ready = page.getByRole("link", { name: /^Download/ }).first();
  await expect(ready).toBeVisible({ timeout: 30_000 });
  const csv = await Promise.all([page.waitForEvent("download"), ready.click()]).then(([d]) => d);
  expect(csv.suggestedFilename()).toMatch(/-records\.csv$/);
  const text = readFileSync((await csv.path()) ?? "", "utf8");
  expect(text.split("\n")[0]).toContain("Winnow ID,Title");
  expect(text).toContain("Melatonin for shift workers");
  await noSeriousA11yProblems(page, "Exports");
  await shot(page, "report-exports");

  // The audit log: owners and admins only.
  await page.getByRole("link", { name: "Audit log" }).click();
  await expect(page.getByText("Ngozi Okafor asked for an export")).toBeVisible();
  await expect(page.getByText(/downloaded an export/).first()).toBeVisible();
  await noSeriousA11yProblems(page, "Audit log");
  await shot(page, "report-audit");
  const reviewerPage = await reviewer.newPage();
  await reviewerPage.goto(`/p/${pid}/report`);
  await expect(reviewerPage.getByRole("link", { name: "Statistics" })).toBeVisible();
  await expect(reviewerPage.getByRole("link", { name: "Audit log" })).toHaveCount(0);

  // Risk of bias: assess an included study with RoB 2, then see it in the plots.
  await page.getByRole("link", { name: "Risk of bias" }).click();
  const studies = page.getByRole("navigation", { name: "Studies" });
  await expect(studies.getByRole("link")).toHaveCount(2);
  await studies.getByRole("link").first().click();
  // One judgement per domain; RoB 2 has five.
  const judgements = page.getByRole("group", { name: "Judgement: Risk of bias" });
  await expect(judgements).toHaveCount(5);
  for (let index = 0; index < 5; index++) {
    await judgements.nth(index).getByText("Low risk").click();
  }
  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();
  await expect(studies.getByText("You have submitted 1 of 2.")).toBeVisible();
  await noSeriousA11yProblems(page, "Risk of bias assessment");
  await shot(page, "rob-assessment");
  await page.getByRole("link", { name: "Summary" }).click();
  await expect(page.getByRole("img", { name: /Traffic-light plot of 1 studies/ })).toBeVisible();
  await page.getByText("The judgements as a table").click();
  await expect(page.getByRole("table", { name: "Judgements by study and domain" })).toContainText("Low risk");
  await noSeriousA11yProblems(page, "Risk of bias summary");
  await shot(page, "rob-summary");

  // A full backup, restored as a new review of the owner's.
  await page.goto(`/p/${pid}/report/exports`);
  await page.getByText("Full backup", { exact: true }).click();
  await page.getByRole("button", { name: "Make a backup" }).click();
  const backupLink = page.getByRole("link", { name: /backup\.zip/ });
  await expect(backupLink).toBeVisible({ timeout: 60_000 });
  const backup = await Promise.all([page.waitForEvent("download"), backupLink.click()]).then(
    ([d]) => d,
  );
  expect(backup.suggestedFilename()).toMatch(/-backup\.zip$/);
  await page.goto("/");
  await page.getByRole("link", { name: "Restore a backup" }).click();
  await page.getByLabel("Backup file (.zip)").setInputFiles((await backup.path()) ?? "");
  await page.getByRole("button", { name: "Restore" }).click();
  await expect(page.getByText(/Restored 6 records/)).toBeVisible({ timeout: 60_000 });
  await noSeriousA11yProblems(page, "Restore");
  await shot(page, "restore-done");
  await page.getByRole("link", { name: "Open the restored review" }).click();
  await expect(page.getByRole("heading", { name: /\(restored\)$/ })).toBeVisible();

  await owner.close();
  await reviewer.close();
});
