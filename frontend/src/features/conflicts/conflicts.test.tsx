import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import type { Project } from "@/api/projects";
import { PROJECT, USER, mockApi, problemResponse, projectRoutes } from "@/test/api";
import { renderApp } from "@/test/render-app";

const signedIn = { "GET /api/v1/auth/me": USER };
const base = `/api/v1/projects/${PROJECT.id}`;

const CONFLICT = {
  record_id: "r1",
  title: "Rotating night shifts and sleep quality in nurses",
  authors: ["Smith, Jane A"],
  year: 2019,
  journal: "Journal of Advanced Nursing",
  abstract: "AIM: to examine whether rotating night shifts affect sleep.",
  doi: "10.1111/jan.13894",
  decisions: [
    { user_id: "u1", name: "Ada Lovelace", decision: "include", reason_ids: [], note: "Adults." },
    {
      user_id: "u2",
      name: "Grace Hopper",
      decision: "exclude",
      reason_ids: ["why1"],
      note: null,
    },
  ],
  notes: [],
  resolution: null,
};

const REASONS = [{ id: "why1", label: "Wrong population", stage: "both", position: 0 }];

function routes(extra: Record<string, unknown> = {}) {
  return {
    ...signedIn,
    ...projectRoutes(),
    [`GET ${base}/exclusion-reasons`]: REASONS,
    [`GET ${base}/conflicts`]: { items: [CONFLICT], next_cursor: null, total: 1 },
    ...extra,
  };
}

describe("conflicts", () => {
  test("the decisions are side by side, and the resolver decides", async () => {
    const server = mockApi(
      routes({ [`POST ${base}/conflicts/r1/resolve`]: { ...CONFLICT, resolution: "exclude" } }),
    );
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/conflicts`);

    const card = within(await screen.findByRole("article"));
    const decisions = within(card.getByRole("list", { name: "Decisions" }));
    expect(decisions.getByText("Ada Lovelace: Included")).toBeVisible();
    expect(decisions.getByText("Grace Hopper: Excluded")).toBeVisible();
    expect(decisions.getByText("Wrong population")).toBeVisible();
    expect(decisions.getByText("“Adults.”")).toBeVisible();

    await user.click(card.getByRole("button", { name: "Wrong population" }));
    await user.type(card.getByLabelText(/Why/), "Children only.");
    await user.click(card.getByRole("button", { name: "Exclude" }));
    expect(await server.calls(`POST ${base}/conflicts/r1/resolve`)[0]?.json()).toEqual({
      stage: "title_abstract",
      final_decision: "exclude",
      reason_ids: ["why1"],
      note: "Children only.",
    });
  });

  test("asking to discuss leaves a note and emails the reviewers", async () => {
    const server = mockApi(
      routes({
        [`POST ${base}/conflicts/r1/discuss`]: {
          id: "n1",
          body: "Is this adults?",
          visibility: "team",
          author: USER.name,
          mine: true,
          created_at: "2026-09-23T10:00:00Z",
        },
      }),
    );
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/conflicts`);

    const card = within(await screen.findByRole("article"));
    await user.type(card.getByLabelText("Discuss"), "Is this adults?");
    await user.click(card.getByRole("button", { name: /Ask them to discuss/ }));
    expect(await screen.findByText(/reviewers have been emailed/)).toBeVisible();
    expect(server.calls(`POST ${base}/conflicts/r1/discuss`)).toHaveLength(1);
  });

  test("the list narrows to where two chosen reviewers disagree, and the abstract opens", async () => {
    const server = mockApi(
      routes({
        [`GET ${base}/members`]: {
          items: [
            {
              user: { id: "u1", name: "Ada Lovelace", email: null },
              role: "owner",
              can_resolve_conflicts: false,
              stages: ["title_abstract"],
              joined_at: "2026-09-20T10:00:00Z",
            },
            {
              user: { id: "u2", name: "Grace Hopper", email: null },
              role: "reviewer",
              can_resolve_conflicts: false,
              stages: ["title_abstract"],
              joined_at: "2026-09-20T10:00:00Z",
            },
          ],
          next_cursor: null,
        },
      }),
    );
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/conflicts`);

    const card = within(await screen.findByRole("article"));
    await user.click(card.getByRole("button", { name: "Read the abstract" }));
    expect(card.getByText(/rotating night shifts affect sleep/)).toBeVisible();

    screen.getByLabelText("Between").focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("option", { name: "Ada Lovelace" }));
    screen.getByLabelText("And").focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("option", { name: "Grace Hopper" }));
    await vi.waitFor(() => {
      const asked = server
        .calls(`GET ${base}/conflicts`)
        .map((request) => new URL(request.url).searchParams.toString());
      expect(
        asked.some((query) => query.includes("reviewer_a=u1") && query.includes("reviewer_b=u2")),
      ).toBe(true);
    });
  });

  test("with nothing to resolve, it says so", async () => {
    mockApi(routes({ [`GET ${base}/conflicts`]: { items: [], next_cursor: null, total: 0 } }));
    renderApp(`/p/${PROJECT.id}/conflicts`);
    expect(await screen.findByText("No conflicts.")).toBeVisible();
  });

  test("a reviewer who does not resolve conflicts is told whose job it is", async () => {
    const asReviewer: Project = {
      ...PROJECT,
      membership: { ...PROJECT.membership, role: "reviewer" },
      permissions: ["view", "screen", "export"],
    };
    const server = mockApi({ ...signedIn, ...projectRoutes(asReviewer) });
    renderApp(`/p/${PROJECT.id}/conflicts`);
    expect(await screen.findByText(/for the review's owners and admins/)).toBeVisible();
    expect(server.calls(`GET ${base}/conflicts`)).toHaveLength(0);
  });
});

describe("bulk decisions", () => {
  test("the count is shown before anything changes, and sent back to confirm it", async () => {
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`GET ${base}/exclusion-reasons`]: REASONS,
      [`POST ${base}/bulk-decision/preview`]: { decided: 12 },
      [`POST ${base}/bulk-decision`]: { decided: 12 },
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/records?q=type:editorial`);

    await user.click(await screen.findByRole("button", { name: /Decide these records/ }));
    const sheet = within(await screen.findByRole("dialog"));
    expect(await sheet.findByText("12 records will be excluded.")).toBeVisible();
    await user.click(sheet.getByRole("button", { name: "Wrong population" }));
    await user.click(sheet.getByRole("button", { name: "Exclude 12 records" }));

    const body = (await server.calls(`POST ${base}/bulk-decision`)[0]?.json()) as Record<
      string,
      unknown
    >;
    expect(body).toMatchObject({
      final_decision: "exclude",
      q: "type:editorial",
      reason_ids: ["why1"],
      expected: 12,
    });
    expect(await screen.findByText("Excluded 12 records.")).toBeVisible();
  });

  test("if the records changed meanwhile, nothing is decided and the new count shows", async () => {
    let previews = 0;
    mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`POST ${base}/bulk-decision/preview`]: () => {
        previews += 1;
        return { decided: previews === 1 ? 12 : 14 };
      },
      [`POST ${base}/bulk-decision`]: () =>
        problemResponse(409, {
          title: "Conflict",
          code: "bulk_changed",
          detail: "The filter now matches 14 records, not 12.",
        }),
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/records`);

    await user.click(await screen.findByRole("button", { name: /Decide these records/ }));
    const sheet = within(await screen.findByRole("dialog"));
    await user.click(await sheet.findByRole("button", { name: "Exclude 12 records" }));
    expect(await sheet.findByText(/now matches 14 records/)).toBeVisible();
    expect(await sheet.findByRole("button", { name: "Exclude 14 records" })).toBeVisible();
  });

  test("reviewers do not see it", async () => {
    const asReviewer: Project = {
      ...PROJECT,
      membership: { ...PROJECT.membership, role: "reviewer" },
      permissions: ["view", "screen", "export"],
    };
    mockApi({ ...signedIn, ...projectRoutes(asReviewer) });
    renderApp(`/p/${PROJECT.id}/records`);
    expect(await screen.findByRole("heading", { name: "Records" })).toBeVisible();
    expect(screen.queryByRole("button", { name: /Decide these records/ })).toBeNull();
  });
});

describe("the review overview", () => {
  test("once there are records, the next step is to continue screening", async () => {
    mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`GET ${base}/records/facets`]: {
        title_abstract: [{ value: "pending", label: "pending", count: 40 }],
        full_text: [],
        years: [],
        imports: [],
        duplicates: 0,
        total: 40,
      },
    });
    renderApp(`/p/${PROJECT.id}`);
    const link = await screen.findByRole("link", { name: /Continue screening/ });
    expect(link).toHaveAttribute("href", `/p/${PROJECT.id}/screen/ta`);
  });
});
