import { vi } from "vitest";

import type { User } from "@/api/auth";

export const READY = { status: "ok", checks: { database: "ok", redis: "ok" } } as const;
export const CSRF = "test-csrf-token";

export const USER: User = {
  id: "0192f0c1-0000-7000-8000-000000000001",
  name: "Ada Lovelace",
  email: "ada@example.org",
  email_verified: true,
  totp_enabled: false,
  recovery_codes_left: 0,
  is_instance_admin: false,
  created_at: "2026-09-01T10:00:00Z",
};

export const OPTIONS = {
  registration: "open",
  single_user: false,
  needs_setup: false,
  email_enabled: true,
} as const;

type Reply = Response | object | (() => Response | object);
type Handler = (request: Request) => Reply | Promise<Reply>;

export function json(body: unknown, status = 200): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function problemResponse(status: number, body: Record<string, unknown>): Response {
  return new Response(JSON.stringify({ status, ...body }), {
    status,
    headers: { "Content-Type": "application/problem+json" },
  });
}

export const signedOut = () =>
  problemResponse(401, {
    title: "Unauthorized",
    code: "not_authenticated",
    detail: "Sign in to continue.",
  });

/**
 * A fake API keyed by "METHOD /path". The defaults describe a healthy, open instance with
 * nobody signed in; tests override the routes they care about. Unknown routes answer 404.
 */
export function mockApi(routes: Record<string, Handler | Reply> = {}) {
  const table: Record<string, Handler | Reply> = {
    "GET /api/v1/readyz": READY,
    "GET /api/v1/auth/csrf": { csrf_token: CSRF },
    "GET /api/v1/auth/options": OPTIONS,
    "GET /api/v1/auth/me": signedOut,
    ...routes,
  };
  const requests: Request[] = [];
  const fetch = vi.fn<typeof globalThis.fetch>(async (input, init) => {
    const request = input instanceof Request ? input : new Request(input, init);
    requests.push(request.clone());
    const route = table[`${request.method} ${new URL(request.url).pathname}`];
    if (route === undefined) return problemResponse(404, { title: "Not Found" });
    let reply = typeof route === "function" ? await (route as Handler)(request) : route;
    if (typeof reply === "function") reply = (reply as () => Response | object)();
    return reply instanceof Response ? reply : json(reply);
  });
  vi.stubGlobal("fetch", fetch);
  return {
    fetch,
    requests,
    /** Requests to one route, oldest first. */
    calls: (key: string) =>
      requests.filter((r) => `${r.method} ${new URL(r.url).pathname}` === key),
  };
}

/** Replace fetch for the rest of the test with one that always gives `response()`. */
export function stubFetch(response: () => Response | Promise<Response>) {
  const fetch = vi.fn<typeof globalThis.fetch>(() => Promise.resolve(response()));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
