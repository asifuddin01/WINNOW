import { readFileSync } from "node:fs";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { addMember, apiSend, createProject, createSignedInUser, importRis } from "../support/api";
import { uniqueEmail } from "../support/mail";

const TITLES = ["Melatonin for night nurses", "Bright light on the ward"];

function ris(): string {
  return TITLES.map((title, index) =>
    [
      "TY  - JOUR",
      `TI  - ${title}`,
      "AU  - Okafor, Ngozi",
      `PY  - ${2018 + index}`,
      "JO  - Sleep Medicine",
      `DO  - 10.1000/extract.${index}`,
      "ER  - ",
    ].join("\n"),
  ).join("\n");
}

async function shot(page: Page, name: string): Promise<void> {
  const folder = process.env.SCREENS;
  if (!folder) return;
  await page.screenshot({ path: `${folder}/${name}.png`, fullPage: true });
  await page.emulateMedia({ colorScheme: "dark" });
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${folder}/${name}-dark.png`, fullPage: true });
  await page.emulateMedia({ colorScheme: "light" });
}

async function noSeriousA11yProblems(page: Page, where: string): Promise<void> {
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

async function include(request: APIRequestContext, url: string, pid: string, rid: string) {
  for (const stage of ["title_abstract", "full_text"]) {
    await apiSend(request, url, "PUT", `/api/v1/projects/${pid}/records/${rid}/decision`, {
      stage,
      decision: "include",
    });
  }
}

/** Phase 8: a form built and published, two extractions reconciled, the data exported. */
test("extraction: build a form, extract twice, reconcile, export", async ({
  browser,
  baseURL,
}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "one journey is enough");
  test.setTimeout(240_000);
  const url = baseURL ?? "";
  const owner = await browser.newContext();
  const reviewer = await browser.newContext();
  const reviewerEmail = uniqueEmail("extract-reviewer");
  await createSignedInUser(owner.request, url, uniqueEmail("extract-owner"), "Ngozi Okafor");
  await createSignedInUser(reviewer.request, url, reviewerEmail, "Elin Lindqvist");
  const pid = await createProject(owner.request, url, `Extraction ${Date.now().toString(36)}`);
  await apiSend(owner.request, url, "PATCH", `/api/v1/projects/${pid}`, {
    settings: { reviewers_per_record_ta: 1, reviewers_per_record_ft: 1 },
  });
  await apiSend(owner.request, url, "PATCH", `/api/v1/projects/${pid}/membership`, {
    keep_blind: false,
  });
  await addMember(owner.request, reviewer.request, url, pid, reviewerEmail);
  await importRis(owner.request, url, pid, ris());
  const records = (await (await owner.request.get(`/api/v1/projects/${pid}/records`)).json()) as {
    items: { id: string; title: string }[];
  };
  const study = records.items.find((r) => r.title === TITLES[0])?.id ?? "";
  await include(owner.request, url, pid, study);

  // Build the form in the builder, and publish it.
  const page = await owner.newPage();
  await page.goto(`/p/${pid}/extraction/forms`);
  await page.getByLabel("New form").fill("Trial data");
  await page.getByLabel("Two extractors per study").check();
  await page.getByRole("button", { name: "Create" }).click();
  const adding = page.getByRole("group", { name: "Add a field" });
  await adding.getByRole("button", { name: "Choice", exact: true }).click();
  await adding.getByRole("button", { name: "Number", exact: true }).click();
  const fields = page.getByRole("list", { name: "Fields" }).getByRole("listitem");
  await fields.nth(0).getByLabel("Label", { exact: true }).fill("Study design");
  await fields.nth(0).getByLabel("Options, one per line").fill("RCT\nCohort");
  await fields.nth(0).getByLabel("Required", { exact: true }).check();
  await fields.nth(1).getByLabel("Label", { exact: true }).fill("Participants");
  await fields.nth(1).getByLabel("Unit", { exact: true }).fill("people");
  await fields.nth(1).getByLabel("Whole numbers only").check();
  await noSeriousA11yProblems(page, "Form builder");
  await shot(page, "extraction-builder");
  await page.getByRole("button", { name: "Publish version 1" }).click();
  await expect(page.getByText("Published. Reviewers can extract with it now.")).toBeVisible();
  const forms = (await (
    await owner.request.get(`/api/v1/projects/${pid}/extraction-forms`)
  ).json()) as { id: string }[];
  const fid = forms[0]?.id ?? "";

  // The owner extracts in the page; the reviewer through the API, differently.
  await page.goto(`/p/${pid}/extraction`);
  await page.getByRole("navigation", { name: "Studies" }).getByRole("link").first().click();
  await page.getByLabel(/Study design/).selectOption("RCT");
  await page.getByLabel(/Participants/).fill("120");
  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();
  await noSeriousA11yProblems(page, "Extract");
  await shot(page, "extraction-entry");
  await apiSend(reviewer.request, url, "PUT", `/api/v1/projects/${pid}/extraction-forms/${fid}/entries/${study}`, {
    data: { study_design: "RCT", participants: 118 },
    status: "submitted",
  });

  // Reconcile: take the reviewer's count.
  await page.goto(`/p/${pid}/extraction/consensus`);
  await page.getByRole("navigation", { name: "Studies to reconcile" }).getByRole("link").first().click();
  await expect(page.getByRole("table", { name: "Values the extractors gave differently" })).toContainText("118");
  await page.getByRole("button", { name: /Use .*value for Participants/ }).nth(1).click();
  await expect(page.getByRole("textbox", { name: /Participants/ })).toHaveValue("118");
  await noSeriousA11yProblems(page, "Consensus");
  await shot(page, "extraction-consensus");
  await page.getByRole("button", { name: "Save consensus" }).click();
  await expect(page.getByText(/Consensus saved/)).toBeVisible();

  // Export the final data, wide, and read it.
  await page.goto(`/p/${pid}/report/exports`);
  await page.getByText("Extracted data", { exact: true }).click();
  await page.getByRole("button", { name: "Make the file" }).click();
  const link = page.getByRole("link", { name: /extraction-trial-data-v1-wide\.csv/ });
  await expect(link).toBeVisible({ timeout: 30_000 });
  const file = await Promise.all([page.waitForEvent("download"), link.click()]).then(([d]) => d);
  const text = readFileSync((await file.path()) ?? "", "utf8");
  expect(text.split("\n")[0]).toContain("record_id,study,extractor,study_design,participants");
  expect(text).toContain("consensus,RCT,118");

  // The methods text says so.
  await page.goto(`/p/${pid}/report/methods`);
  await expect(page.getByLabel("Methods text")).toHaveValue(
    /Two reviewers extracted data independently and resolved differences\./,
  );
  await noSeriousA11yProblems(page, "Methods text");
  await shot(page, "report-methods");

  await owner.close();
  await reviewer.close();
});
