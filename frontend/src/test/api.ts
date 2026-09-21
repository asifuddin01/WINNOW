import { vi } from "vitest";

export const READY = { status: "ok", checks: { database: "ok", redis: "ok" } } as const;

/** Replace fetch for the rest of the test with one that always gives `response()`. */
export function stubFetch(response: () => Response | Promise<Response>) {
  const fetch = vi.fn<typeof globalThis.fetch>(() => Promise.resolve(response()));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

export function problemResponse(status: number, body: Record<string, unknown>): Response {
  return new Response(JSON.stringify({ status, ...body }), {
    status,
    headers: { "Content-Type": "application/problem+json" },
  });
}
