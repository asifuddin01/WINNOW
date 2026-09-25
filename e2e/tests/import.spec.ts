import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { PASSWORD, createProject, createSignedInUser } from "../support/api";
import { uniqueEmail } from "../support/mail";

/** A small RIS export, the shape PubMed and Ovid send. */
function ris(count: number, from = 0): string {
  const entries = [];
  for (let index = from + 1; index <= from + count; index++) {
    entries.push(
      [
        "TY  - JOUR",
        `TI  - Rotating night shifts and sleep quality in nurses, part ${index}`,
        "AU  - Smith, Jane A",
        "AU  - Chowdhury, Sara",
        `PY  - ${2015 + (index % 8)}`,
        "JO  - Journal of Advanced Nursing",
        `DO  - 10.1111/jan.${13000 + index}`,
        "AB  - AIM: to examine whether rotating night shifts affect sleep quality.",
        "KW  - nurses",
        "KW  - shift work",
        "ER  - ",
      ].join("\n"),
    );
  }
  // One entry with nothing to identify it: the import reports it and carries on.
  entries.push(["TY  - JOUR", "AU  - Nobody", "ER  - "].join("\n"));
  return `${entries.join("\n")}\n`;
}

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "My reviews" })).toBeVisible();
}

/**
 * Phase 3 acceptance: a search export is read before anything is kept, imported in the
 * background with live progress, and the records can then be searched, filtered and read.
 */
test("a search export is previewed, imported and then searchable", async ({
  page,
  request,
  baseURL,
  isMobile,
}) => {
  test.setTimeout(180_000);
  const owner = uniqueEmail("importer");
  await createSignedInUser(request, baseURL ?? "", owner, "Ada Lovelace");
  const pid = await createProject(request, baseURL ?? "", `Shift work ${Date.now().toString(36)}`);
  await signIn(page, owner);

  await page.goto(`/p/${pid}/import`);
  await page.getByLabel("Search string").fill("nurses AND shift work");
  // A search leaves a database in several files; they go up together (guide 8.3).
  await page.getByLabel("Search export files").setInputFiles([
    {
      name: "pubmed_part1.ris",
      mimeType: "application/x-research-info-systems",
      buffer: Buffer.from(ris(15), "utf8"),
    },
    {
      name: "pubmed_part2.ris",
      mimeType: "application/x-research-info-systems",
      buffer: Buffer.from(ris(10, 100), "utf8"),
    },
  ]);
  await expect(page.getByText("2 files ready")).toBeVisible();
  // Winnow names the database from the file name, so twenty files do not need twenty edits.
  await expect(page.getByLabel("Database for pubmed_part1.ris")).toContainText("PubMed");
  await page.getByRole("button", { name: /Upload and preview 2 files/ }).click();

  // Nothing is in the review yet: this is what Winnow read from each file.
  await expect(page.getByText("pubmed_part1.ris", { exact: true })).toBeVisible();
  await expect(page.getByText("pubmed_part2.ris", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Check" }).first().click();
  await expect(page.getByRole("heading", { name: "The first records Winnow read" })).toBeVisible();
  await expect(page.getByText("part 1", { exact: false }).first()).toBeVisible();

  await page.getByRole("button", { name: "Import all 2 files" }).click();

  // The worker imports in the background; the stream says when it is done. Each file is
  // its own import, so PRISMA can count them and either can be undone on its own.
  await expect(page.getByText("Imported", { exact: true }).first()).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByText("Imported", { exact: true })).toHaveCount(2);
  await expect(page.getByText("15 records", { exact: false })).toBeVisible();
  await expect(page.getByText("10 records", { exact: false })).toBeVisible();
  await expect(page.getByText(/Search: nurses AND shift work/).first()).toBeVisible();

  // And they are there to read. On a phone the review's navigation is behind the sheet.
  if (isMobile) {
    await page.getByRole("banner").getByRole("button", { name: "Toggle sidebar" }).click();
  }
  await page
    .getByRole("navigation", { name: "This review" })
    .getByRole("link", { name: "Records" })
    .click();
  await expect(page).toHaveURL(new RegExp(`/p/${pid}/records$`));
  await expect(page.getByText("25 records")).toBeVisible();

  await page.getByLabel("Search", { exact: true }).fill('"night shifts" author:smith');
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page).toHaveURL(/q=/);
  const rows = page.getByRole("region", { name: "Records" }).getByRole("button");
  await expect(rows.first()).toBeVisible();

  await rows.first().click();
  const detail = page.getByRole("article");
  await expect(detail.getByText(/rotating night shifts affect sleep quality/i)).toBeVisible();
  await expect(detail.getByText("shift work", { exact: true })).toBeVisible();

  // The filters carry their own counts, from the facets endpoint.
  const filters = page.getByRole("navigation", { name: "Filters" });
  await expect(filters.getByRole("button", { name: /All records\s*25/ })).toBeVisible();

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag22aa"])
    .analyze();
  const serious = results.violations.filter(
    (violation) => violation.impact === "serious" || violation.impact === "critical",
  );
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
});

test("a file Winnow cannot read is refused, and nothing is imported", async ({
  page,
  request,
  baseURL,
}) => {
  const owner = uniqueEmail("badfile");
  await createSignedInUser(request, baseURL ?? "", owner, "Grace Hopper");
  const pid = await createProject(request, baseURL ?? "", `Bad file ${Date.now().toString(36)}`);
  await signIn(page, owner);

  await page.goto(`/p/${pid}/import`);
  await page.getByLabel("Search export files").setInputFiles({
    name: "holiday.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("We went to the seaside and it rained.\n", "utf8"),
  });
  await page.getByRole("button", { name: /Upload and preview/ }).click();

  await expect(page.getByText(/could not read/i).first()).toBeVisible();
  await expect(page.getByText("Nothing imported yet", { exact: false })).toBeVisible();
});
