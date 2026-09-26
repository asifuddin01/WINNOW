import { execSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

import {
  addMember,
  apiPost,
  apiSend,
  createProject,
  createSignedInUser,
  importRis,
} from "../support/api";
import { uniqueEmail } from "../support/mail";

/**
 * The accessibility audit (guide 14, Phase 9). Every page, with a review that has
 * something on every page, in light and dark, at each breakpoint the guide names:
 *
 * - axe (WCAG 2.0/2.1/2.2 A and AA, and its best practices): no serious or critical
 *   violation anywhere;
 * - nothing scrolls sideways at 360 px;
 * - on touch screens, every control is at least 44 × 44 px (links inside a sentence
 *   excepted, as WCAG excepts them);
 * - everything the keyboard reaches shows where focus is.
 *
 * Findings of every impact are collected before anything is asserted, so one run lists
 * them all; `A11Y_REPORT=<folder>` also writes them as JSON.
 */

const VIEWPORTS = [
  { width: 360, height: 780, touch: true },
  { width: 768, height: 1024, touch: true },
  { width: 1024, height: 768, touch: false },
  { width: 1440, height: 900, touch: false },
] as const;

const TITLES = [
  "Night shifts and sleep in nurses",
  "Rotating rosters and fatigue",
  "Melatonin for shift workers",
  "Circadian disruption in paramedics",
  "Caffeine and night-time alertness",
  "Light therapy on the ward",
  "Napping on night duty: a randomised trial",
  "Sleep hygiene education for junior doctors",
];

function ris(entries: { title: string; doi: string | null; year: number }[]): string {
  return entries
    .map(({ title, doi, year }) =>
      [
        "TY  - JOUR",
        `TI  - ${title}`,
        "AU  - Okafor, Ngozi",
        "AU  - Lindqvist, Elin",
        `PY  - ${year}`,
        "JO  - Sleep Medicine",
        ...(doi ? [`DO  - ${doi}`] : []),
        "AB  - Whether night work changes how long and how well hospital staff sleep.",
        "KW  - sleep",
        "ER  - ",
      ].join("\n"),
    )
    .join("\n");
}

interface Review {
  state: Awaited<ReturnType<import("@playwright/test").BrowserContext["storageState"]>>;
  pid: string;
  fid: string;
  study: string;
  conflict: string;
}

async function decide(
  request: APIRequestContext,
  url: string,
  pid: string,
  rid: string,
  decision: string,
  stage = "title_abstract",
): Promise<void> {
  await apiSend(request, url, "PUT", `/api/v1/projects/${pid}/records/${rid}/decision`, {
    stage,
    decision,
  });
}

/** A review with something on every page: duplicates, a conflict, full texts to screen,
 * an extraction form with two different extractions, and an instance admin to own it. */
async function makeReview(browser: Browser, url: string): Promise<Review> {
  const owner = await browser.newContext();
  const reviewer = await browser.newContext();
  const ownerEmail = uniqueEmail("a11y-owner");
  const reviewerEmail = uniqueEmail("a11y-reviewer");
  await createSignedInUser(owner.request, url, ownerEmail, "Ngozi Okafor");
  await createSignedInUser(reviewer.request, url, reviewerEmail, "Elin Lindqvist");
  execSync(
    `docker compose exec -T db psql -U winnow -d winnow -c "update users set is_instance_admin = true where email = '${ownerEmail}'"`,
    { stdio: "ignore", cwd: ".." },
  );

  const pid = await createProject(owner.request, url, `Audit ${Date.now().toString(36)}`);
  await apiSend(owner.request, url, "PATCH", `/api/v1/projects/${pid}`, {
    settings: { reviewers_per_record_ta: 2, reviewers_per_record_ft: 1 },
  });
  await apiSend(owner.request, url, "PATCH", `/api/v1/projects/${pid}/membership`, {
    keep_blind: false,
  });
  await addMember(owner.request, reviewer.request, url, pid, reviewerEmail);
  await importRis(
    owner.request,
    url,
    pid,
    ris(TITLES.map((title, index) => ({ title, doi: `10.1000/audit.${index}`, year: 2016 + index }))),
  );
  // The same napping trial from another database, without its DOI: a pair for a person.
  await importRis(
    owner.request,
    url,
    pid,
    ris([{ title: "Napping on night duty: a randomised crossover trial", doi: null, year: 2022 }]),
  );

  const records = (await (await owner.request.get(`/api/v1/projects/${pid}/records`)).json()) as {
    items: { id: string; title: string }[];
  };
  const id = (title: string) => records.items.find((r) => r.title === title)?.id ?? "";
  // 0-3 included by both, 4 a conflict, 5 excluded by both; 6 and 7 left to screen.
  for (const [index, title] of TITLES.slice(0, 6).entries()) {
    await decide(owner.request, url, pid, id(title), index === 5 ? "exclude" : "include");
    await decide(reviewer.request, url, pid, id(title), index >= 4 ? "exclude" : "include");
  }
  const study = id(TITLES[0]);
  await decide(owner.request, url, pid, study, "include", "full_text");

  const form = (await apiPost(owner.request, url, `/api/v1/projects/${pid}/extraction-forms`, {
    name: "Trial data",
    dual: true,
    schema: {
      fields: [
        {
          key: "design",
          label: "Study design",
          type: "select",
          required: true,
          options: ["RCT", "Cohort"],
        },
        { key: "n", label: "Participants", type: "number", unit: "people", integer: true },
        {
          key: "outcomes",
          label: "Outcomes per arm",
          type: "table",
          max_rows: 5,
          columns: [
            { key: "arm", label: "Arm", type: "short_text" },
            { key: "mean", label: "Mean", type: "number" },
          ],
        },
      ],
    },
  })) as { id: string };
  await apiPost(owner.request, url, `/api/v1/projects/${pid}/extraction-forms/${form.id}/publish`, {});
  for (const [request, n] of [
    [owner.request, 120],
    [reviewer.request, 118],
  ] as const) {
    await apiSend(
      request,
      url,
      "PUT",
      `/api/v1/projects/${pid}/extraction-forms/${form.id}/entries/${study}`,
      { data: { design: "RCT", n }, status: "submitted" },
    );
  }

  const state = await owner.storageState();
  await owner.close();
  await reviewer.close();
  return { state, pid, fid: form.id, study, conflict: id(TITLES[4]) };
}

interface Stop {
  name: string;
  path: string;
  /** Open something on the page first: a dialog, a menu. */
  open?: (page: Page) => Promise<void>;
}

function signedInStops({ pid, fid, study, conflict }: Review): Stop[] {
  const p = `/p/${pid}`;
  return [
    { name: "My reviews", path: "/" },
    {
      name: "Notifications",
      path: "/",
      open: async (page) => {
        await page.getByRole("button", { name: /^Notifications/ }).click();
        await expect(page.getByRole("menu")).toBeVisible();
      },
    },
    { name: "New review", path: "/new" },
    { name: "Account", path: "/account" },
    { name: "Restore a backup", path: "/restore" },
    { name: "Admin: people", path: "/admin" },
    { name: "Admin: settings", path: "/admin/settings" },
    { name: "Admin: health", path: "/admin/health" },
    { name: "Page not found", path: "/no-such-page" },
    { name: "Overview", path: p },
    {
      name: "Command palette",
      path: p,
      open: async (page) => {
        await page.keyboard.press("ControlOrMeta+k");
        await expect(page.getByRole("dialog")).toBeVisible();
      },
    },
    { name: "Import", path: `${p}/import` },
    { name: "Duplicates", path: `${p}/duplicates` },
    { name: "Screen titles and abstracts", path: `${p}/screen/ta` },
    { name: "Screen full texts", path: `${p}/screen/ft` },
    { name: "Conflicts", path: `${p}/conflicts` },
    { name: "A conflict", path: `${p}/conflicts?record=${conflict}` },
    { name: "Records", path: `${p}/records` },
    { name: "A record", path: `${p}/records?record=${study}` },
    { name: "Extract", path: `${p}/extraction` },
    { name: "Extract a study", path: `${p}/extraction?form=${fid}&study=${study}` },
    { name: "Extraction forms", path: `${p}/extraction/forms?form=${fid}` },
    { name: "Consensus", path: `${p}/extraction/consensus?form=${fid}&study=${study}` },
    { name: "Risk of bias", path: `${p}/rob` },
    { name: "Risk of bias: a study", path: `${p}/rob?study=${study}` },
    { name: "Report: PRISMA", path: `${p}/report` },
    { name: "Report: statistics", path: `${p}/report/stats` },
    { name: "Report: methods text", path: `${p}/report/methods` },
    { name: "Report: exports", path: `${p}/report/exports` },
    { name: "Report: audit log", path: `${p}/report/audit` },
    { name: "Settings: review", path: `${p}/settings` },
    { name: "Settings: criteria", path: `${p}/settings/criteria` },
    { name: "Settings: keywords", path: `${p}/settings/keywords` },
    { name: "Settings: labels", path: `${p}/settings/labels` },
    { name: "Settings: exclusion reasons", path: `${p}/settings/reasons` },
    { name: "Settings: screening", path: `${p}/settings/screening` },
    { name: "Settings: team", path: `${p}/settings/team` },
  ];
}

const SIGNED_OUT: Stop[] = [
  { name: "Sign in", path: "/login" },
  { name: "Create an account", path: "/register" },
  { name: "Forgot password", path: "/forgot" },
  { name: "Reset password", path: "/reset/not-a-real-token" },
  { name: "Confirm email", path: "/verify/not-a-real-token" },
  { name: "Invitation", path: "/invite/not-a-real-token" },
];

interface Finding {
  page: string;
  viewport: number;
  theme: "light" | "dark";
  kind: "axe" | "overflow" | "touch" | "focus" | "load";
  impact: string;
  rule: string;
  help: string;
  targets: string[];
}

/** Wait for the page to finish arriving: its heading, its data, its toasts. */
async function settle(page: Page): Promise<void> {
  await expect(page.locator("h1").first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/^Loading/)).toHaveCount(0, { timeout: 30_000 });
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0, { timeout: 30_000 });
  await expect
    .poll(() =>
      page
        .locator("[data-sonner-toast]")
        .evaluateAll((toasts) => toasts.every((toast) => getComputedStyle(toast).opacity === "1")),
    )
    .toBe(true);
}

async function axe(page: Page, where: Omit<Finding, "kind" | "impact" | "rule" | "help" | "targets">) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
    .analyze();
  return results.violations.map(
    (violation): Finding => ({
      ...where,
      kind: "axe",
      impact: violation.impact ?? "unknown",
      rule: violation.id,
      help: violation.help,
      targets: violation.nodes.slice(0, 5).map((node) => node.target.join(" ")),
    }),
  );
}

/** What sticks out past the right edge of a 360 px screen (scroll areas excepted). */
function overflow(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    if (document.documentElement.scrollWidth <= width + 1) return [];
    const scrolls = (el: Element) => {
      for (let node = el.parentElement; node; node = node.parentElement) {
        const x = getComputedStyle(node).overflowX;
        if (x === "auto" || x === "scroll" || x === "hidden") return true;
      }
      return false;
    };
    return [...document.body.querySelectorAll("*")]
      .filter((el) => el.getBoundingClientRect().right > width + 1 && !scrolls(el))
      .slice(0, 5)
      .map((el) => `${el.tagName.toLowerCase()}.${[...el.classList].slice(0, 3).join(".")}`);
  });
}

/** Controls whose hit area is smaller than 44 × 44 px, described so they can be found. */
function smallTargets(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const selector = [
      "a[href]",
      "button",
      "input:not([type=hidden])",
      "select",
      "textarea",
      "summary",
      "[role=button]",
      "[role=checkbox]",
      "[role=radio]",
      "[role=switch]",
      "[role=tab]",
      "[role=menuitem]",
      "[role=option]",
      "[role=combobox]",
      "[role=slider]",
    ].join(",");
    const small: string[] = [];
    for (const el of document.querySelectorAll<HTMLElement>(selector)) {
      const style = getComputedStyle(el);
      let box = el.getBoundingClientRect();
      if (box.width <= 1 || box.height <= 1 || style.visibility === "hidden") continue;
      // Visually hidden until focused (the skip link): not something to tap.
      if (style.clip === "rect(0px, 0px, 0px, 0px)" || style.clipPath === "inset(50%)") continue;
      if (el.closest("[inert], [aria-hidden=true]")) continue;
      if ((el as HTMLButtonElement).disabled) continue;
      // WCAG's inline exception: a link inside a sentence is as tall as the sentence.
      const inSentence = [...(el.parentElement?.childNodes ?? [])].some(
        (node) => node.nodeType === Node.TEXT_NODE && Boolean(node.textContent?.trim()),
      );
      if (el.tagName === "A" && (style.display === "inline" || inSentence)) continue;
      if (box.width >= 44 && box.height >= 44) continue;
      // A checkbox or radio is tapped through its label, when the label is big enough.
      const labels = [...((el as HTMLInputElement).labels ?? [])];
      if (
        labels.some((label) => {
          const area = label.getBoundingClientRect();
          return area.width >= 44 && area.height >= 44 && label.contains(el);
        })
      )
        continue;
      // The hit area can be larger than the box (a label around it, an ::after): try the
      // corners of a 44 px square around its middle.
      el.scrollIntoView({ block: "center", inline: "center" });
      box = el.getBoundingClientRect();
      const [x, y] = [box.left + box.width / 2, box.top + box.height / 2];
      const hits = (dx: number, dy: number) =>
        document
          .elementsFromPoint(x + dx, y + dy)
          .some((node) => node === el || (node instanceof HTMLLabelElement && node.control === el));
      if (hits(-21.5, -21.5) && hits(21.5, -21.5) && hits(-21.5, 21.5) && hits(21.5, 21.5))
        continue;
      const name =
        el.getAttribute("aria-label") ??
        (el.textContent?.trim() || el.getAttribute("placeholder") || el.getAttribute("name") || "");
      small.push(
        `${el.getAttribute("role") ?? el.tagName.toLowerCase()} "${name.slice(0, 40)}" ${Math.round(box.width)}×${Math.round(box.height)}`,
      );
    }
    return small;
  });
}

/** Tab through the page; list what takes focus without showing it. */
async function unseenFocus(page: Page): Promise<string[]> {
  await page.locator("body").focus();
  const unseen: string[] = [];
  const seen = new Set<string>();
  for (let step = 0; step < 60; step++) {
    await page.keyboard.press("Tab");
    const focus = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || el === document.body) return null;
      const shows = (node: Element) => {
        const style = getComputedStyle(node);
        const outline = style.outlineStyle !== "none" && parseFloat(style.outlineWidth) > 0;
        return outline || style.boxShadow !== "none";
      };
      // A ring may be drawn by the element or by a wrapper that watches it (:focus-within).
      let visible = shows(el);
      for (let node = el.parentElement, depth = 0; !visible && node && depth < 3; depth++) {
        visible = shows(node) && node.matches(":focus-within");
        node = node.parentElement;
      }
      const box = el.getBoundingClientRect();
      const key = `${el.tagName}|${el.getAttribute("aria-label") ?? el.textContent?.trim().slice(0, 30)}|${Math.round(box.x)},${Math.round(box.y)}`;
      return { key, visible, label: key.split("|").slice(0, 2).join(" ") };
    });
    if (!focus || seen.has(focus.key)) break;
    seen.add(focus.key);
    if (!focus.visible) unseen.push(focus.label);
  }
  return unseen;
}

/** One page, all checks; a page that never finishes loading is a finding too. */
async function audit(
  page: Page,
  stop: Stop,
  viewport: (typeof VIEWPORTS)[number],
): Promise<Finding[]> {
  try {
    return await checks(page, stop, viewport);
  } catch {
    // The development stack compiles pages on first visit and shares the machine with the
    // browsers; one slow load is not a finding, two are.
  }
  try {
    return await checks(page, stop, viewport);
  } catch (error) {
    return [
      {
        page: stop.name,
        viewport: viewport.width,
        theme: "light",
        kind: "load",
        impact: "serious",
        rule: "page-did-not-settle",
        help: String(error).split("\n")[0] ?? "",
        targets: [],
      },
    ];
  }
}

async function checks(
  page: Page,
  stop: Stop,
  viewport: (typeof VIEWPORTS)[number],
): Promise<Finding[]> {
  const findings: Finding[] = [];
  const where = { page: stop.name, viewport: viewport.width };
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto(stop.path);
  // The pointer stays where an earlier page clicked; a control measured under it is
  // hovered, and part-way through its hover transition (a false contrast failure).
  await page.mouse.move(0, 0);
  await settle(page);
  if (stop.open) await stop.open(page);

  for (const theme of ["light", "dark"] as const) {
    if (theme === "dark") {
      await page.emulateMedia({ colorScheme: "dark" });
      // Colours ease between themes; measure once they have.
      await page.waitForTimeout(600);
    }
    findings.push(...(await axe(page, { ...where, theme })));
  }
  const base = { ...where, theme: "light" as const, impact: "serious", help: "" };
  if (viewport.width === 360) {
    const wide = await overflow(page);
    if (wide.length)
      findings.push({ ...base, kind: "overflow", rule: "no-sideways-scroll", targets: wide });
  }
  if (viewport.touch) {
    expect(await page.evaluate(() => matchMedia("(pointer: coarse)").matches), "a touch screen").toBe(true);
    const small = await smallTargets(page);
    if (small.length)
      findings.push({ ...base, kind: "touch", rule: "target-44px", targets: small });
  }
  if (viewport.width === 1440 && !stop.open) {
    const unseen = await unseenFocus(page);
    if (unseen.length)
      findings.push({ ...base, kind: "focus", rule: "focus-visible", targets: unseen });
  }
  return findings;
}

function report(findings: Finding[], name: string): string {
  const folder = process.env.A11Y_REPORT;
  if (folder) {
    mkdirSync(folder, { recursive: true });
    writeFileSync(`${folder}/${name}.json`, JSON.stringify(findings, null, 2));
  }
  return findings
    .map((f) => `${f.viewport} ${f.theme} ${f.page}: [${f.kind} ${f.impact}] ${f.rule} ${f.help}\n    ${f.targets.join("\n    ")}`)
    .join("\n");
}

function failures(findings: Finding[]): Finding[] {
  return findings.filter(
    (f) => f.kind !== "axe" || f.impact === "serious" || f.impact === "critical",
  );
}

test("reduced motion is respected: nothing eases or animates", async ({ browser }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "once is enough");
  const still = await browser.newContext({ reducedMotion: "reduce" });
  const page = await still.newPage();
  await page.goto("/login");
  const button = page.getByRole("button", { name: "Sign in", exact: true });
  await expect(button).toBeVisible();
  const seconds = (value: string) => Math.max(...value.split(",").map((part) => parseFloat(part)));
  const style = await button.evaluate((el) => {
    const computed = getComputedStyle(el);
    return { transition: computed.transitionDuration, animation: computed.animationDuration };
  });
  expect(seconds(style.transition)).toBeLessThan(0.001);
  expect(seconds(style.animation)).toBeLessThan(0.001);
  await still.close();
});

test.describe("accessibility audit", () => {
  test.describe.configure({ mode: "parallel" });
  let review: Review | undefined;

  test.beforeAll(async ({ browser, baseURL }, testInfo) => {
    if (testInfo.project.name !== "desktop") return;
    test.setTimeout(180_000);
    review = await makeReview(browser, baseURL ?? "");
  });

  for (const viewport of VIEWPORTS) {
    test(`every page at ${viewport.width} px, light and dark`, async ({ browser }, testInfo) => {
      test.skip(testInfo.project.name !== "desktop", "the audit sets its own viewports");
      test.setTimeout(900_000);
      const size = { width: viewport.width, height: viewport.height };
      const touch = { hasTouch: viewport.touch, isMobile: viewport.touch };
      const findings: Finding[] = [];

      const visitor = await browser.newContext({ viewport: size, ...touch });
      const out = await visitor.newPage();
      for (const stop of SIGNED_OUT) findings.push(...(await audit(out, stop, viewport)));
      await visitor.close();

      const owner = await browser.newContext({ viewport: size, ...touch, storageState: review?.state });
      const page = await owner.newPage();
      for (const stop of signedInStops(review as Review))
        findings.push(...(await audit(page, stop, viewport)));
      await owner.close();

      const text = report(findings, `a11y-${viewport.width}`);
      await testInfo.attach(`findings at ${viewport.width} px`, { body: text || "none" });
      if (text) console.log(text);
      expect(failures(findings).length, report(failures(findings), `a11y-${viewport.width}-failures`)).toBe(0);
    });
  }
});
