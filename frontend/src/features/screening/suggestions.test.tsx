import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import type { Project } from "@/api/projects";
import { OPTIONS, PROJECT, USER, mockApi, problemResponse, projectRoutes } from "@/test/api";
import { renderApp } from "@/test/render-app";

const signedIn = { "GET /api/v1/auth/me": USER };
const base = `/api/v1/projects/${PROJECT.id}`;
const withAi = { ...OPTIONS, llm_available: true, llm_provider: "anthropic" };
const aiOn: Project = { ...PROJECT, settings: { ...PROJECT.settings, llm_assist_enabled: true } };
const RECORD = {
  id: "r1",
  title: "Rotating night shifts and sleep in nurses",
  authors: [],
  year: 2020,
  journal: null,
  volume: null,
  issue: null,
  pages: null,
  doi: null,
  pmid: null,
  url: null,
  abstract: "Nurses on rotating nights slept less.",
  keywords: [],
  publication_type: [],
  relevance_score: null,
  my_decision: null,
  labels: [],
  notes: [],
  others: null,
};
const SUGGESTION = {
  id: "s1",
  record_id: "r1",
  stage: "title_abstract",
  decision: "include",
  confidence: 0.75,
  criteria: [
    { criterion_id: "c1", kind: "inclusion", text: "Adults on night shifts", verdict: "met" },
    { criterion_id: "c2", kind: "exclusion", text: "Case reports", verdict: "unclear" },
  ],
  rationale: "Nurses on rotating nights; the design is not stated.",
  provider: "anthropic",
  model: "claude-opus-5",
  created_at: "2026-09-23T10:00:00Z",
};

function routes(extra: Record<string, unknown> = {}) {
  return {
    ...signedIn,
    ...projectRoutes(aiOn),
    "GET /api/v1/auth/options": withAi,
    [`GET ${base}/screening/queue`]: { items: [RECORD] },
    [`GET ${base}/records/r1/llm-suggest`]: { suggestion: null },
    ...extra,
  };
}

describe("AI suggestions while screening", () => {
  test("say where the record goes, and show the answer as advice", async () => {
    const server = mockApi(routes({ [`POST ${base}/records/r1/llm-suggest`]: SUGGESTION }));
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/screen/ta`);

    const box = within(await screen.findByRole("region", { name: "AI suggestion" }));
    expect(box.getByText(/to Anthropic \(Claude\)\. It is advice/)).toBeVisible();
    await user.click(box.getByRole("button", { name: "Ask for a suggestion" }));

    expect(await box.findByText(/Suggests/)).toHaveTextContent("Suggests Include, 75% sure");
    const criteria = within(box.getByRole("list", { name: "Criteria" }));
    expect(criteria.getByText("met:")).toBeVisible();
    expect(criteria.getByText("unclear:")).toBeVisible();
    expect(box.getByText(/the design is not stated/)).toBeVisible();
    expect(box.getByRole("button", { name: "Ask again" })).toBeVisible();
    expect(server.calls(`POST ${base}/records/r1/llm-suggest`)).toHaveLength(1);
    // Nothing was decided.
    expect(server.calls(`PUT ${base}/records/r1/decision`)).toHaveLength(0);
  });

  test("a provider that fails says why", async () => {
    mockApi(
      routes({
        [`POST ${base}/records/r1/llm-suggest`]: () =>
          problemResponse(502, {
            title: "Bad Gateway",
            code: "llm_failed",
            detail: "The AI provider is busy. Try again in a minute.",
          }),
      }),
    );
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/screen/ta`);
    const box = within(await screen.findByRole("region", { name: "AI suggestion" }));
    await user.click(box.getByRole("button", { name: "Ask for a suggestion" }));
    expect(await box.findByRole("alert")).toHaveTextContent("The AI provider is busy");
  });

  test("with the review's AI switched off there is nothing to ask", async () => {
    mockApi({
      ...signedIn,
      ...projectRoutes(),
      "GET /api/v1/auth/options": withAi,
      [`GET ${base}/screening/queue`]: { items: [RECORD] },
    });
    renderApp(`/p/${PROJECT.id}/screen/ta`);
    expect(await screen.findByRole("heading", { name: RECORD.title })).toBeVisible();
    expect(screen.queryByRole("region", { name: "AI suggestion" })).toBeNull();
  });
});

describe("the AI setting", () => {
  test("only the owner can switch it on", async () => {
    const asAdmin: Project = {
      ...PROJECT,
      membership: { ...PROJECT.membership, role: "admin" },
    };
    mockApi({ ...signedIn, ...projectRoutes(asAdmin), "GET /api/v1/auth/options": withAi });
    renderApp(`/p/${PROJECT.id}/settings/screening`);
    expect(await screen.findByText(/only they can turn this on/)).toBeVisible();
    expect(screen.getByRole("switch", { name: /AI suggestions/ })).toBeDisabled();
  });

  test("once it is on, admins can download every suggestion", async () => {
    mockApi({ ...signedIn, ...projectRoutes(aiOn), "GET /api/v1/auth/options": withAi });
    renderApp(`/p/${PROJECT.id}/settings/screening`);
    expect(
      await screen.findByRole("link", { name: /Download every AI suggestion/ }),
    ).toHaveAttribute("href", `${base}/llm-suggestions.csv`);
    await vi.waitFor(() => {
      expect(screen.getByRole("switch", { name: /AI suggestions/ })).toBeEnabled();
    });
  });
});
