import { queryOptions, type QueryClient } from "@tanstack/react-query";

import { ApiError, api, unwrap } from "@/api/client";
import { forgetCsrfToken, setCsrfToken } from "@/api/csrf";
import type { components } from "@/api/schema";

export type User = components["schemas"]["UserOut"];
export type AuthOptions = components["schemas"]["AuthOptions"];
export type SessionInfo = components["schemas"]["SessionOut"];
export type TwoFactorSetup = components["schemas"]["TwoFactorSetupOut"];

export const authKeys = {
  me: ["auth", "me"] as const,
  options: ["auth", "options"] as const,
  sessions: ["auth", "sessions"] as const,
};

/** The signed-in user, or null when signed out (a 401 is an answer, not an error). */
export const meQuery = queryOptions({
  queryKey: authKeys.me,
  queryFn: async ({ signal }): Promise<User | null> => {
    const result = await api.GET("/api/v1/auth/me", { signal });
    if (result.response.status === 401) return null;
    return unwrap(result);
  },
  staleTime: 60_000,
});

export const authOptionsQuery = queryOptions({
  queryKey: authKeys.options,
  queryFn: async ({ signal }) => unwrap(await api.GET("/api/v1/auth/options", { signal })),
  staleTime: 5 * 60_000,
});

/** For route guards: the cached answer if there is one, otherwise fetch it. */
export function loadMe(queryClient: QueryClient): Promise<User | null> {
  return queryClient.query({ ...meQuery, staleTime: "static" });
}

export function loadAuthOptions(queryClient: QueryClient): Promise<AuthOptions> {
  return queryClient.query({ ...authOptionsQuery, staleTime: "static" });
}

export const sessionsQuery = queryOptions({
  queryKey: authKeys.sessions,
  queryFn: async ({ signal }) => unwrap(await api.GET("/api/v1/auth/sessions", { signal })),
});

/** After a sign-in or session rotation: remember the new token and the user. */
function signedIn(queryClient: QueryClient, body: { csrf_token: string; user?: User }): void {
  setCsrfToken(body.csrf_token);
  if (body.user) queryClient.setQueryData(authKeys.me, body.user);
}

export async function signIn(
  queryClient: QueryClient,
  input: { email: string; password: string; totp?: string },
): Promise<User> {
  const body = unwrap(await api.POST("/api/v1/auth/login", { body: input }));
  signedIn(queryClient, body);
  return body.user;
}

export async function setUpAdmin(
  queryClient: QueryClient,
  input: { name: string; email: string; password: string },
): Promise<User> {
  const body = unwrap(await api.POST("/api/v1/auth/setup", { body: input }));
  signedIn(queryClient, body);
  await queryClient.invalidateQueries({ queryKey: authKeys.options });
  return body.user;
}

export async function register(input: {
  name: string;
  email: string;
  password: string;
  invite_token?: string;
}) {
  return unwrap(await api.POST("/api/v1/auth/register", { body: input }));
}

export async function verifyEmail(queryClient: QueryClient, token: string): Promise<User> {
  const user = unwrap(await api.POST("/api/v1/auth/verify-email", { body: { token } }));
  await queryClient.invalidateQueries({ queryKey: authKeys.me });
  return user;
}

export async function resendVerification() {
  return unwrap(await api.POST("/api/v1/auth/verify-email/resend"));
}

export async function forgotPassword(email: string) {
  return unwrap(await api.POST("/api/v1/auth/password/forgot", { body: { email } }));
}

export async function resetPassword(token: string, password: string): Promise<void> {
  unwrap(await api.POST("/api/v1/auth/password/reset", { body: { token, password } }));
}

export async function changePassword(
  queryClient: QueryClient,
  input: { current_password: string; new_password: string },
): Promise<void> {
  signedIn(queryClient, unwrap(await api.POST("/api/v1/auth/password/change", { body: input })));
  await queryClient.invalidateQueries({ queryKey: authKeys.sessions });
}

/** Forget everything about the signed-in user in this tab. */
export function clearAuth(queryClient: QueryClient): void {
  forgetCsrfToken();
  queryClient.setQueryData(authKeys.me, null);
  queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== "auth" });
  queryClient.removeQueries({ queryKey: authKeys.sessions });
}

export async function signOut(
  queryClient: QueryClient,
  { everywhere = false } = {},
): Promise<void> {
  const path = everywhere ? "/api/v1/auth/logout-all" : "/api/v1/auth/logout";
  unwrap(await api.POST(path));
  clearAuth(queryClient);
}

export async function revokeSession(queryClient: QueryClient, id: string): Promise<void> {
  unwrap(
    await api.DELETE("/api/v1/auth/sessions/{session_id}", {
      params: { path: { session_id: id } },
    }),
  );
  await queryClient.invalidateQueries({ queryKey: authKeys.sessions });
}

export async function beginTwoFactorSetup(): Promise<TwoFactorSetup> {
  return unwrap(await api.POST("/api/v1/auth/2fa/setup"));
}

export async function enableTwoFactor(queryClient: QueryClient, code: string): Promise<string[]> {
  const body = unwrap(await api.POST("/api/v1/auth/2fa/enable", { body: { code } }));
  signedIn(queryClient, body);
  await queryClient.invalidateQueries({ queryKey: authKeys.me });
  return body.recovery_codes;
}

export async function disableTwoFactor(
  queryClient: QueryClient,
  input: { password: string; code: string },
): Promise<void> {
  signedIn(queryClient, unwrap(await api.POST("/api/v1/auth/2fa/disable", { body: input })));
  await queryClient.invalidateQueries({ queryKey: authKeys.me });
}

export async function regenerateRecoveryCodes(
  queryClient: QueryClient,
  code: string,
): Promise<string[]> {
  const body = unwrap(await api.POST("/api/v1/auth/2fa/recovery-codes", { body: { code } }));
  await queryClient.invalidateQueries({ queryKey: authKeys.me });
  return body.recovery_codes;
}

export type Provider = "google" | "orcid";
export const PROVIDER_NAMES: Record<Provider, string> = { google: "Google", orcid: "ORCID" };

/** Where a "Continue with Google/ORCID" link starts; a browser navigation, not a fetch. */
export function startUrl(provider: Provider, redirect?: string): string {
  const target = safeRedirect(redirect);
  const start = `/api/v1/auth/${provider}/start`;
  return target === "/" ? start : `${start}?redirect=${encodeURIComponent(target)}`;
}

/** Finish a Google or ORCID sign-in on an account with two-factor authentication. */
export async function finishExternalSignIn(
  queryClient: QueryClient,
  provider: Provider,
  code: string,
): Promise<{ user: User; redirect: string }> {
  const path =
    provider === "orcid" ? "/api/v1/auth/orcid/two-factor" : "/api/v1/auth/google/two-factor";
  const body = unwrap(await api.POST(path, { body: { code } }));
  signedIn(queryClient, body);
  return { user: body.user, redirect: safeRedirect(body.redirect) };
}

/** What went wrong in a Google or ORCID sign-in, from the `?error=` the callback sends. */
export const SIGN_IN_ERRORS: Record<string, string> = {
  google_state:
    "That Google sign-in expired, or was started in another browser. Try again from this page.",
  google_cancelled: "Google sign-in was cancelled.",
  google_failed: "Google sign-in did not finish. Try again, or sign in with your password.",
  google_unverified: "Google has not verified that email address, so it cannot be used to sign in.",
  registration_closed:
    "No Winnow account uses that Google address, and this instance is not accepting new accounts.",
  orcid_state:
    "That ORCID sign-in expired, or was started in another browser. Try again from this page.",
  orcid_cancelled: "ORCID sign-in was cancelled.",
  orcid_failed: "ORCID sign-in did not finish. Try again, or sign in with your password.",
  orcid_not_linked:
    "No Winnow account is linked to that ORCID iD. Sign in another way, then link your iD from Account.",
  account_disabled: "This account is disabled. Ask your Winnow administrator.",
};

/** Start linking an ORCID iD to this account: the browser goes to ORCID and comes back. */
export async function linkOrcid(): Promise<void> {
  const { url } = unwrap(await api.POST("/api/v1/auth/orcid/link"));
  window.location.assign(url);
}

export async function unlinkOrcid(queryClient: QueryClient): Promise<void> {
  unwrap(await api.DELETE("/api/v1/auth/orcid"));
  await queryClient.invalidateQueries({ queryKey: authKeys.me });
}

/** How a link came back to the account page, from its `?orcid=`. */
export const ORCID_LINK_RESULTS: Record<string, string> = {
  linked: "Your ORCID iD is linked. You can now sign in with ORCID.",
  orcid_taken: "That ORCID iD is already linked to another Winnow account.",
  orcid_cancelled: "Linking was cancelled at ORCID.",
  orcid_failed: "ORCID did not confirm the iD. Try again.",
};

/** An error from the API, optionally with one particular `code`. */
export function isApiError(error: unknown, code?: string): error is ApiError {
  return error instanceof ApiError && (code === undefined || error.code === code);
}

/**
 * Where to go after signing in. Only same-site paths: `?redirect=https://evil.example`
 * or `//evil.example` would otherwise turn the sign-in page into an open redirect.
 */
export function safeRedirect(target: unknown): string {
  if (typeof target !== "string" || !target.startsWith("/") || target.startsWith("//")) return "/";
  if (target.startsWith("/\\") || /^\/(login|register|setup|forgot|reset|verify)\b/.test(target)) {
    return "/";
  }
  return target;
}
