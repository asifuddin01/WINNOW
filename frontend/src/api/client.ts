import createClient from "openapi-fetch";

import type { components, paths } from "@/api/schema";

export type Problem = components["schemas"]["Problem"];

/**
 * Typed client for the Winnow API. Same origin only: the session cookie (Phase 1)
 * travels automatically and no token is ever stored in JavaScript.
 */
export const api = createClient<paths>({
  baseUrl: window.location.origin,
  credentials: "same-origin",
  // Resolve fetch per call rather than capturing it at import, so tests can stub it.
  fetch: (request) => globalThis.fetch(request),
  headers: { Accept: "application/json, application/problem+json" },
});

/** An API error with the server's RFC 9457 problem details, when it sent any. */
export class ApiError extends Error {
  readonly status: number;
  readonly problem: Problem | null;

  constructor(status: number, problem: Problem | null) {
    super(problem?.detail ?? problem?.title ?? `Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.problem = problem;
  }

  /** Quote this when reporting the error; it matches the server's log line. */
  get requestId(): string | null {
    return this.problem?.request_id ?? null;
  }
}

function isProblem(body: unknown): body is Problem {
  return (
    typeof body === "object" &&
    body !== null &&
    typeof (body as Problem).title === "string" &&
    typeof (body as Problem).status === "number"
  );
}

/** Unwraps an openapi-fetch result: the data, or an ApiError carrying the problem. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || result.data === undefined) {
    throw new ApiError(result.response.status, isProblem(result.error) ? result.error : null);
  }
  return result.data;
}
