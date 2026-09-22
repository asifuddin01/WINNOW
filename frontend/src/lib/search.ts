/** `?redirect=` on the sign-in page; anything else is ignored. Kept free of zod so the
 * route definitions that use it do not pull the form library into the first bundle. */
export function redirectSearch(search: Record<string, unknown>): { redirect?: string } {
  return typeof search.redirect === "string" ? { redirect: search.redirect } : {};
}
