/**
 * The CSRF token for writes (guide 12.1). Kept in memory only, never in web storage.
 * The server binds it to the session, so it is replaced after every sign-in and forgotten
 * after sign-out; the next write fetches a fresh one.
 */
let token: string | null = null;
let pending: Promise<string> | null = null;

export function setCsrfToken(next: string): void {
  token = next;
}

export function forgetCsrfToken(): void {
  token = null;
}

export async function csrfToken(): Promise<string> {
  if (token) return token;
  pending ??= (async () => {
    const response = await globalThis.fetch(`${window.location.origin}/api/v1/auth/csrf`, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`Could not get a security token (${response.status})`);
    const body = (await response.json()) as { csrf_token: string };
    token = body.csrf_token;
    return token;
  })().finally(() => {
    pending = null;
  });
  return pending;
}
