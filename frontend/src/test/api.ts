import { vi } from "vitest";

import type { User } from "@/api/auth";
import type { Member, Project } from "@/api/projects";

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
  has_password: true,
  google_linked: false,
  orcid: null,
  created_at: "2026-09-01T10:00:00Z",
};

export const PROJECT: Project = {
  id: "0192f0c1-0000-7000-8000-00000000aaa1",
  title: "Shift work and sleep quality",
  description: null,
  review_type: "systematic",
  research_question: "Do night shifts affect sleep quality in nurses?",
  pico: { population: "Nurses", intervention: null, comparator: null, outcome: null },
  status: "setup",
  settings: {
    blind_mode: true,
    reviewers_per_record_ta: 2,
    reviewers_per_record_ft: 2,
    maybe_counts_as: "include",
    require_reason_on_exclude_ta: false,
    require_reason_on_exclude_ft: true,
    ranking_enabled: true,
    llm_assist_enabled: false,
    stopping_rule: { type: "consecutive_excludes", n: 200 },
    assignment: "all",
    highlight_keywords: true,
    dedup_on_import: true,
    dedup_auto_resolve: true,
  },
  owner: { id: USER.id, name: USER.name, email: USER.email },
  membership: {
    role: "owner",
    can_resolve_conflicts: false,
    stages: ["title_abstract", "full_text"],
    keep_blind: true,
  },
  permissions: [
    "view",
    "screen",
    "see_others_while_blind",
    "resolve_conflicts",
    "import",
    "edit_setup",
    "manage_members",
    "edit_settings",
    "export",
    "delete_project",
  ],
  member_count: 1,
  created_at: "2026-09-20T10:00:00Z",
  updated_at: "2026-09-21T10:00:00Z",
};

export const OWNER_MEMBER: Member = {
  user: { id: USER.id, name: USER.name, email: USER.email },
  role: "owner",
  can_resolve_conflicts: false,
  stages: ["title_abstract", "full_text"],
  joined_at: "2026-09-20T10:00:00Z",
};

/** What a review answers with before anything has been added to it. */
export function projectRoutes(project: Project = PROJECT, members: Member[] = [OWNER_MEMBER]) {
  const base = `/api/v1/projects/${project.id}`;
  return {
    "GET /api/v1/projects": { items: [summaryOf(project)], next_cursor: null },
    [`GET ${base}`]: project,
    [`GET ${base}/members`]: { items: members, next_cursor: null },
    [`GET ${base}/invites`]: [],
    [`GET ${base}/criteria`]: [],
    [`GET ${base}/keyword-groups`]: [],
    [`GET ${base}/exclusion-reasons`]: [],
    [`GET ${base}/labels`]: [],
    [`GET ${base}/records`]: { items: [], next_cursor: null, total: 0, total_is_exact: true },
    [`GET ${base}/records/facets`]: {
      title_abstract: [],
      full_text: [],
      years: [],
      imports: [],
      duplicates: 0,
      total: 0,
    },
    [`GET ${base}/imports`]: [],
    [`GET ${base}/dedup/summary`]: {
      pending: 0,
      certain: 0,
      resolved: 0,
      ignored: 0,
      duplicates: 0,
    },
    [`GET ${base}/dedup/clusters`]: [],
    [`GET ${base}/screening/queue`]: { items: [] },
    [`GET ${base}/screening/progress`]: {
      stage: "title_abstract",
      screened: 0,
      total: 0,
      remaining: 0,
      included: 0,
      excluded: 0,
      maybe: 0,
      conflicts: 0,
      blind: false,
      can_resolve: true,
      assignment: "all",
    },
    [`GET ${base}/my-history`]: { items: [], next_cursor: null },
    [`GET ${base}/conflicts`]: { items: [], next_cursor: null, total: 0 },
    [`GET ${base}/ranking/status`]: RANKING_STATUS,
    [`GET ${base}/ranking/curve`]: {
      stage: "title_abstract",
      total: 0,
      mine: { screened: 0, found_at: [] },
      team: null,
    },
    [`GET ${base}/screening/stopping`]: {
      stage: "title_abstract",
      rule: "consecutive_excludes",
      threshold: 200,
      in_a_row: 0,
      remaining: 0,
      estimate: null,
    },
  };
}

/** A review with ranking on and no model yet. */
export const RANKING_STATUS = {
  stage: "title_abstract",
  enabled: true,
  model: null,
  needs_each: 1,
  have_included: 0,
  have_excluded: 0,
  retrain_after: 25,
  training: false,
  explore_every: 20,
} as const;

export function summaryOf(project: Project) {
  return {
    id: project.id,
    title: project.title,
    review_type: project.review_type,
    status: project.status,
    role: project.membership.role,
    member_count: project.member_count,
    last_activity_at: project.updated_at,
    created_at: project.created_at,
  };
}

export const OPTIONS = {
  registration: "open",
  single_user: false,
  needs_setup: false,
  email_enabled: true,
  google_enabled: false,
  orcid_enabled: false,
} as const;

type Reply = Response | object | (() => Response | object);
type Handler = (request: RecordedRequest) => Reply | Promise<Reply>;

/** What a test can ask about a call the app made. */
export interface RecordedRequest extends Request {
  /** The form data, when the call was a file upload rather than JSON. */
  form?: FormData;
}

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
    "GET /api/v1/projects": { items: [], next_cursor: null },
    ...routes,
  };
  const requests: RecordedRequest[] = [];
  const fetch = vi.fn<typeof globalThis.fetch>(async (input, init) => {
    const request = record(input, init);
    requests.push(request);
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

/**
 * The call as something a test can read twice. A Request cannot be built around jsdom's
 * FormData, so an upload is recorded without its body and the form is kept beside it.
 */
function record(input: RequestInfo | URL, init?: RequestInit): RecordedRequest {
  if (init?.body instanceof FormData) {
    const url = input instanceof Request ? input.url : input.toString();
    const request: RecordedRequest = new Request(url, {
      method: init.method ?? "POST",
      headers: init.headers,
    });
    request.form = init.body;
    return request;
  }
  const request = input instanceof Request ? input : new Request(input, init);
  return request.clone();
}

/** Replace fetch for the rest of the test with one that always gives `response()`. */
export function stubFetch(response: () => Response | Promise<Response>) {
  const fetch = vi.fn<typeof globalThis.fetch>(() => Promise.resolve(response()));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
