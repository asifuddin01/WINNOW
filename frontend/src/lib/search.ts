/** `?redirect=` on the sign-in page; anything else is ignored. Kept free of zod so the
 * route definitions that use it do not pull the form library into the first bundle. */
export function redirectSearch(search: Record<string, unknown>): { redirect?: string } {
  return typeof search.redirect === "string" ? { redirect: search.redirect } : {};
}

/** The sign-in page's query: where to go next, and what a Google sign-in reported. */
export function signInSearch(search: Record<string, unknown>): {
  redirect?: string;
  error?: string;
  step?: "google-2fa";
} {
  return {
    ...redirectSearch(search),
    ...(typeof search.error === "string" && { error: search.error }),
    ...(search.step === "google-2fa" && { step: "google-2fa" as const }),
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
} {
  const status = TA_STATUSES.find((value) => value === search.status);
  const sort = RECORD_SORTS.find((value) => value === search.sort);
  return {
    ...(typeof search.q === "string" && search.q ? { q: search.q.slice(0, 500) } : {}),
    ...(status ? { status } : {}),
    ...(typeof search.batch === "string" ? { batch: search.batch } : {}),
    ...(search.duplicates === true || search.duplicates === "true" ? { duplicates: true } : {}),
    ...(sort ? { sort } : {}),
  };
}
