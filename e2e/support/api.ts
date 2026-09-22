import { execSync } from "node:child_process";

import type { APIRequestContext } from "@playwright/test";

import { emailedLink } from "./mail";

export const PASSWORD = "an end to end passphrase";

/** Write to the API the way the SPA does: same Origin, CSRF token from /auth/csrf. */
export async function apiPost(
  request: APIRequestContext,
  baseURL: string,
  path: string,
  data: unknown,
): Promise<void> {
  const { csrf_token } = (await (await request.get("/api/v1/auth/csrf")).json()) as {
    csrf_token: string;
  };
  const response = await request.post(`/api/v1/auth${path}`, {
    data,
    headers: { "X-CSRF-Token": csrf_token, Origin: baseURL },
  });
  if (!response.ok())
    throw new Error(`${path} answered ${response.status()}: ${await response.text()}`);
}

/**
 * Registration is limited to five an hour per address (guide 12.6) and the whole suite
 * comes from one, so the counter is cleared before each account it makes. The limit itself
 * is exercised by the backend security tests.
 */
export function clearRegistrationLimits(): void {
  execSync(
    `docker compose exec -T redis sh -c "redis-cli --scan --pattern 'rl:register-ip:*' | xargs -r redis-cli del"`,
    { stdio: "ignore", cwd: ".." },
  );
}

/** A verified account, signed in within `request`'s cookie jar. */
export async function createSignedInUser(
  request: APIRequestContext,
  baseURL: string,
  email: string,
  name = "Grace Hopper",
): Promise<void> {
  clearRegistrationLimits();
  await apiPost(request, baseURL, "/register", { name, email, password: PASSWORD });
  const verify = await emailedLink(request, email, "verify");
  await apiPost(request, baseURL, "/verify-email", { token: verify.split("/").pop() });
  await apiPost(request, baseURL, "/login", { email, password: PASSWORD });
}
