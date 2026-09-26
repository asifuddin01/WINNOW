const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** `?redirect=` on the sign-in page; anything else is ignored. Kept free of zod so the
 * route definitions that use it do not pull the form library into the first bundle. */
export function redirectSearch(search: Record<string, unknown>): { redirect?: string } {
  return typeof search.redirect === "string" ? { redirect: search.redirect } : {};
}

/** The sign-in page's query: where to go next, and what a Google sign-in reported. */
export function signInSearch(search: Record<string, unknown>): {
  redirect?: string;
  error?: string;
  step?: "google-2fa" | "orcid-2fa";
} {
  return {
    ...redirectSearch(search),
    ...(typeof search.error === "string" && { error: search.error }),
    ...((search.step === "google-2fa" || search.step === "orcid-2fa") && { step: search.step }),
  };
}

export type WizardStep = "basics" | "criteria" | "team";

/** The create-review wizard remembers where it is in the URL, so a reload resumes. */
export function wizardSearch(search: Record<string, unknown>): {
  project?: string;
  step?: WizardStep;
} {
  const steps: WizardStep[] = ["basics", "criteria", "team"];
  return {
    ...(typeof search.project === "string" && { project: search.project }),
    ...(typeof search.step === "string" &&
      steps.includes(search.step as WizardStep) && { step: search.step as WizardStep }),
  };
}

/** `?invite=` on the sign-up page: the token that lets an invited address register. */
export function inviteSearch(search: Record<string, unknown>): { invite?: string } {
  return typeof search.invite === "string" ? { invite: search.invite } : {};
}

const RECORD_SORTS = ["added", "oldest", "year", "year_asc", "title", "relevance"] as const;
const TA_STATUSES = ["pending", "included", "excluded", "maybe", "conflict"] as const;

/** The records table keeps its search, filters and order in the URL, so a link shares them. */
export function recordsSearch(search: Record<string, unknown>): {
  q?: string;
  status?: (typeof TA_STATUSES)[number];
  batch?: string;
  duplicates?: boolean;
  sort?: (typeof RECORD_SORTS)[number];
  record?: string;
} {
  const status = TA_STATUSES.find((value) => value === search.status);
  const sort = RECORD_SORTS.find((value) => value === search.sort);
  return {
    ...(typeof search.record === "string" && UUID.test(search.record) && { record: search.record }),
    ...(typeof search.q === "string" && search.q ? { q: search.q.slice(0, 500) } : {}),
    ...(status ? { status } : {}),
    ...(typeof search.batch === "string" ? { batch: search.batch } : {}),
    ...(search.duplicates === true || search.duplicates === "true" ? { duplicates: true } : {}),
    ...(sort ? { sort } : {}),
  };
}

const SCREEN_SORTS = ["relevance", "random", "year", "title", "added"] as const;

/** The screening page keeps its order and search in the URL, so a reload resumes them. */
export function screenSearch(search: Record<string, unknown>): {
  sort?: (typeof SCREEN_SORTS)[number];
  q?: string;
} {
  const sort = SCREEN_SORTS.find((value) => value === search.sort);
  return {
    ...(sort ? { sort } : {}),
    ...(typeof search.q === "string" && search.q ? { q: search.q.slice(0, 500) } : {}),
  };
}

/** Full-text screening adds `?view=pdfs`: the stage's PDFs rather than the next record. */
export function fullTextSearch(
  search: Record<string, unknown>,
): ReturnType<typeof screenSearch> & { view?: "pdfs" } {
  return { ...screenSearch(search), ...(search.view === "pdfs" && { view: "pdfs" as const }) };
}

export const ROB_TOOLS = ["rob2", "robins_i", "nos", "quadas2"] as const;
export type RobToolKey = (typeof ROB_TOOLS)[number];

/** The risk-of-bias page: which tool, and which study is open. */
export function robSearch(search: Record<string, unknown>): { tool?: RobToolKey; study?: string } {
  return {
    ...(typeof search.tool === "string" &&
      (ROB_TOOLS as readonly string[]).includes(search.tool) && {
        tool: search.tool as RobToolKey,
      }),
    ...(typeof search.study === "string" &&
      /^[0-9a-f-]{36}$/i.test(search.study) && { study: search.study }),
  };
}

/** The extraction pages: which form version, and which study is open. */
export function extractionSearch(search: Record<string, unknown>): {
  form?: string;
  study?: string;
} {
  return {
    ...(typeof search.form === "string" && UUID.test(search.form) && { form: search.form }),
    ...(typeof search.study === "string" && UUID.test(search.study) && { study: search.study }),
  };
}
