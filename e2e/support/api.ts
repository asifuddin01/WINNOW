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
): Promise<unknown> {
  const { csrf_token } = (await (await request.get("/api/v1/auth/csrf")).json()) as {
    csrf_token: string;
  };
  const url = path.startsWith("/api/") ? path : `/api/v1/auth${path}`;
  const response = await request.post(url, {
    data,
    headers: { "X-CSRF-Token": csrf_token, Origin: baseURL },
  });
  if (!response.ok())
    throw new Error(`${path} answered ${response.status()}: ${await response.text()}`);
  return response.status() === 204 ? null : await response.json();
}

/** A review owned by whoever `request` is signed in as; returns its id. */
export async function createProject(
  request: APIRequestContext,
  baseURL: string,
  title: string,
): Promise<string> {
  const project = (await apiPost(request, baseURL, "/api/v1/projects", { title })) as {
    id: string;
  };
  return project.id;
}

/**
 * Registration is limited to five an hour per address, and confirming an email to twenty
 * (guide 12.6), and the whole suite comes from one address, so both counters are cleared
 * before each account it makes. The limits themselves are exercised by the backend
 * security tests.
 */
export function clearRegistrationLimits(): void {
  execSync(
    `docker compose exec -T redis sh -c "redis-cli --scan --pattern 'rl:register-ip:*' | xargs -r redis-cli del; redis-cli --scan --pattern 'rl:verify-email-ip:*' | xargs -r redis-cli del"`,
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

/** Invite `email` to the review and have `joiner` (already signed in) accept. */
export async function addMember(
  owner: APIRequestContext,
  joiner: APIRequestContext,
  baseURL: string,
  pid: string,
  email: string,
  role = "reviewer",
): Promise<void> {
  const invite = (await apiPost(owner, baseURL, `/api/v1/projects/${pid}/invites`, {
    email,
    role,
  })) as { link: string };
  const token = invite.link.split("/").pop() ?? "";
  await apiPost(joiner, baseURL, `/api/v1/invites/${token}/accept`, {});
}

/** Put a search export into the review through the same upload and confirm the app uses,
 * and wait for the worker to finish it. */
export async function importRis(
  request: APIRequestContext,
  baseURL: string,
  pid: string,
  ris: string,
): Promise<void> {
  const { csrf_token } = (await (await request.get("/api/v1/auth/csrf")).json()) as {
    csrf_token: string;
  };
  const uploaded = await request.post(`/api/v1/projects/${pid}/imports`, {
    headers: { "X-CSRF-Token": csrf_token, Origin: baseURL },
    multipart: {
      files: {
        name: "search.ris",
        mimeType: "application/x-research-info-systems",
        buffer: Buffer.from(ris),
      },
      database_name: "PubMed",
    },
  });
  if (!uploaded.ok())
    throw new Error(`upload answered ${uploaded.status()}: ${await uploaded.text()}`);
  const { batches } = (await uploaded.json()) as { batches: { id: string }[] };
  const batch = batches[0]?.id ?? "";
  await apiPost(request, baseURL, `/api/v1/projects/${pid}/imports/${batch}/confirm`, {});
  for (let attempt = 0; attempt < 60; attempt++) {
    const history = (await (await request.get(`/api/v1/projects/${pid}/imports`)).json()) as {
      id: string;
      status: string;
    }[];
    if (history.find((item) => item.id === batch)?.status === "done") return;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error("the import did not finish");
}
