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
