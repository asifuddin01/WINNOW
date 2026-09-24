import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { apiSend, createProject, createSignedInUser, importRis } from "../support/api";
import { MAILPIT, uniqueEmail } from "../support/mail";
import { EICAR, eicarPdf, makeZip, tinyPdf, zipBomb } from "../support/pdf";

const PAPERS = [
  { title: "Kidney stone detection on low-dose CT", doi: "10.1000/ft.kidney" },
  { title: "Renal cysts and automated volumetry", doi: "10.1000/ft.cysts" },
  { title: "Ureteric calculi in emergency imaging", doi: "10.1000/ft.ureter" },
];

function ris(): string {
  return PAPERS.map((paper, index) =>
    [
      "TY  - JOUR",
      `TI  - ${paper.title}`,
      "AU  - Okafor, Ngozi",
      `PY  - ${2019 + index}`,
      "JO  - Radiology",
      `DO  - ${paper.doi}`,
      "AB  - An abstract about imaging the kidney.",
      "ER  - ",
    ].join("\n"),
  ).join("\n");
}

/** A review whose records have all been included at title and abstract; returns the ids. */
async function reviewAtFullText(
  request: APIRequestContext,
  baseURL: string,
  label: string,
): Promise<{ pid: string; ids: Record<string, string> }> {
  const pid = await createProject(request, baseURL, `${label} ${Date.now().toString(36)}`);
  await apiSend(request, baseURL, "PATCH", `/api/v1/projects/${pid}`, {
    settings: { reviewers_per_record_ta: 1, reviewers_per_record_ft: 1 },
  });
  await importRis(request, baseURL, pid, ris());
  const records = (await (await request.get(`/api/v1/projects/${pid}/records`)).json()) as {
    items: { id: string; title: string }[];
  };
  const ids: Record<string, string> = {};
  for (const record of records.items) {
    ids[record.title] = record.id;
    await apiSend(request, baseURL, "PUT", `/api/v1/projects/${pid}/records/${record.id}/decision`, {
      stage: "title_abstract",
      decision: "include",
    });
  }
  return { pid, ids };
}

async function uploadPdf(
  request: APIRequestContext,
  baseURL: string,
  pid: string,
  rid: string,
  name: string,
  buffer: Buffer,
): Promise<void> {
  const { csrf_token } = (await (await request.get("/api/v1/auth/csrf")).json()) as {
    csrf_token: string;
  };
  const response = await request.post(`/api/v1/projects/${pid}/records/${rid}/fulltext`, {
    headers: { "X-CSRF-Token": csrf_token, Origin: baseURL },
    multipart: { file: { name, mimeType: "application/pdf", buffer } },
  });
  if (!response.ok()) throw new Error(`upload answered ${response.status()}`);
}

async function scanStatus(request: APIRequestContext, pid: string, rid: string) {
  const state = (await (
    await request.get(`/api/v1/projects/${pid}/records/${rid}/fulltext`)
  ).json()) as { fulltext: { scan_status: string } | null };
  return state.fulltext?.scan_status;
}

async function noSeriousA11yProblems(page: Page, where: string): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag22aa"])
    .analyze();
  const serious = results.violations.filter(
    (violation) => violation.impact === "serious" || violation.impact === "critical",
  );
  expect(serious, `${where}: ${JSON.stringify(serious, null, 2)}`).toEqual([]);
}

/**
 * Phase 7 acceptance, part one: a PDF carrying the EICAR test file is scanned by the real
 * ClamAV and quarantined, and the owner is told.
 */
test("a PDF carrying the EICAR test file is quarantined", async ({ browser, baseURL }) => {
  test.setTimeout(180_000);
  const url = baseURL ?? "";
  const context = await browser.newContext();
  const page = await context.newPage();
  const email = uniqueEmail("ft-eicar");
  await createSignedInUser(context.request, url, email, "Ngozi Okafor");
  const { pid, ids } = await reviewAtFullText(context.request, url, "Quarantine");
  const rid = ids[PAPERS[0]!.title]!;

  // The bare EICAR file is not a PDF: refused at the door, never stored.
  const { csrf_token } = (await (await context.request.get("/api/v1/auth/csrf")).json()) as {
    csrf_token: string;
  };
  const bare = await context.request.post(`/api/v1/projects/${pid}/records/${rid}/fulltext`, {
    headers: { "X-CSRF-Token": csrf_token, Origin: url },
    multipart: { file: { name: "eicar.pdf", mimeType: "application/pdf", buffer: EICAR } },
  });
  expect(bare.status()).toBe(415);

  await uploadPdf(context.request, url, pid, rid, "innocent.pdf", eicarPdf());
  await expect
    .poll(() => scanStatus(context.request, pid, rid), { timeout: 60_000 })
    .toBe("infected");

  await page.goto(`/p/${pid}/screen/ft?view=pdfs`);
  const row = page.getByRole("listitem").filter({ hasText: PAPERS[0]!.title });
  await expect(row.getByText("Quarantined")).toBeVisible();
  await row.getByRole("button", { name: new RegExp(`^${PAPERS[0]!.title}`) }).click();
  await expect(page.getByRole("alert").getByText("This PDF was quarantined.")).toBeVisible();
  // Its link is refused, so there is nothing to open or download.
  const link = await context.request.get(`/api/v1/projects/${pid}/records/${rid}/fulltext/url`);
  expect(link.status()).toBe(409);

  // The owner was emailed.
  await expect
    .poll(
      async () => {
        const found = (await (
          await context.request.get(
            `${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:"${email}"`)}`,
          )
        ).json()) as { messages: { Subject: string }[] };
        return found.messages.map((message) => message.Subject);
      },
      { timeout: 30_000 },
    )
    .toContain("A PDF in your review was quarantined");
  await context.close();
});

/** Part two: a ZIP bomb is rejected, while a ZIP of PDFs is matched and attached. */
test("a ZIP bomb is rejected; a ZIP of PDFs is matched and attached", async ({
  browser,
  baseURL,
}) => {
  test.setTimeout(180_000);
  const url = baseURL ?? "";
  const context = await browser.newContext();
  const page = await context.newPage();
  await createSignedInUser(context.request, url, uniqueEmail("ft-zip"), "Ngozi Okafor");
  const { pid, ids } = await reviewAtFullText(context.request, url, "ZIPs");

  await page.goto(`/p/${pid}/screen/ft?view=pdfs`);
  const zipInput = page.locator('input[type="file"][accept*="zip"]');
  await zipInput.setInputFiles({
    name: "papers.zip",
    mimeType: "application/zip",
    buffer: zipBomb(),
  });
  await expect(page.getByRole("alert")).toContainText("looks like a ZIP bomb");

  await zipInput.setInputFiles({
    name: "papers.zip",
    mimeType: "application/zip",
    buffer: makeZip({
      "10.1000_ft.kidney.pdf": tinyPdf([["Kidney stone detection"]]),
      "Okafor 2020 renal cysts.pdf": tinyPdf([["Renal cysts"]]),
      "readme.txt": Buffer.from("not a paper"),
    }),
  });
  await expect(page.getByText("Sure match by DOI")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Likely match by author and year")).toBeVisible();
  await page.getByRole("button", { name: "Attach 2 PDFs" }).click();
  await expect(page.getByText(/2 PDFs attached/)).toBeVisible();
  for (const title of [PAPERS[0]!.title, PAPERS[1]!.title]) {
    await expect
      .poll(() => scanStatus(context.request, pid, ids[title]!), { timeout: 60_000 })
      .toBe("clean");
  }
  await page.reload();
  await expect(page.getByText("With PDF").first()).toBeVisible();
  await noSeriousA11yProblems(page, "PDFs view");
  await context.close();
});

/**
 * Part three: the viewer works on a phone — the PDF fits the screen, search finds its
 * words, zoom works, and a selection becomes a highlight.
 */
test("the PDF viewer works on a 360-pixel phone", async ({ browser, baseURL }) => {
  test.setTimeout(180_000);
  const url = baseURL ?? "";
  const context = await browser.newContext({
    viewport: { width: 360, height: 740 },
    hasTouch: true,
    isMobile: true,
  });
  const page = await context.newPage();
  await createSignedInUser(context.request, url, uniqueEmail("ft-phone"), "Ngozi Okafor");
  const { pid, ids } = await reviewAtFullText(context.request, url, "Phone");
  const rid = ids[PAPERS[0]!.title]!;
  await uploadPdf(
    context.request,
    url,
    pid,
    rid,
    "Okafor 2019.pdf",
    tinyPdf([
      ["Kidney stone detection on low-dose CT", "Methods: 120 patients, kidney stones"],
      ["Results", "Sensitivity for kidney stones was 0.94"],
    ]),
  );
  await expect
    .poll(() => scanStatus(context.request, pid, rid), { timeout: 60_000 })
    .toBe("clean");

  await page.goto(`/p/${pid}/screen/ft?view=pdfs`);
  await page.getByRole("button", { name: new RegExp(`^${PAPERS[0]!.title}`) }).click();
  const viewer = page.getByRole("document", { name: /page 1 of 2/ });
  await expect(viewer).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".textLayer").first()).toContainText("Kidney stone detection");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);

  const search = page.getByRole("searchbox", { name: "Search in the PDF" });
  await search.fill("kidney");
  await search.press("Enter");
  await expect(page.getByText(/^1 of 3$/)).toBeVisible();
  await page.getByRole("button", { name: "Next match" }).click();
  await expect(page.getByText(/^2 of 3$/)).toBeVisible();

  const zoom = page.getByText(/^\d+%$/);
  const before = await zoom.textContent();
  await page.getByRole("button", { name: "Zoom in" }).click();
  await expect(zoom).not.toHaveText(before ?? "");

  await page.locator(".textLayer span", { hasText: "Sensitivity" }).first().selectText();
  const toolbar = page.getByRole("toolbar", { name: "Highlight the selected text" });
  await toolbar.getByRole("button", { name: "Green" }).click();
  await expect(page.getByRole("button", { name: /Highlights.*\(1\)/ })).toBeVisible();
  await expect(page.locator(".winnow-annotation").first()).toBeAttached();
  await context.close();
});
