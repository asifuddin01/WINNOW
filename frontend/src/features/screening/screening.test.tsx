import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import type { Project } from "@/api/projects";
import { PROJECT, USER, json, mockApi, problemResponse, projectRoutes } from "@/test/api";
import { setMedia } from "@/test/media";
import { renderApp } from "@/test/render-app";

const signedIn = { "GET /api/v1/auth/me": USER };
const base = `/api/v1/projects/${PROJECT.id}`;
const page = `/p/${PROJECT.id}/screen/ta`;

function item(index: number, overrides: Record<string, unknown> = {}) {
  return {
    id: `r${index}`,
    title: `Night shifts and sleep, study ${index}`,
    authors: ["Smith, Jane A"],
    year: 2020,
    journal: "Sleep Medicine",
    volume: null,
    issue: null,
    pages: null,
    doi: `10.1000/sleep.${index}`,
    pmid: null,
    url: null,
    abstract: `Nurses on rotating night shifts slept less in study ${index}.`,
    keywords: [],
    publication_type: [],
    relevance_score: null,
    my_decision: null,
    labels: [],
    notes: [],
    others: null,
    ...overrides,
  };
}

const REASONS = [
  { id: "why1", label: "Wrong population", stage: "both", position: 0 },
  { id: "why2", label: "Wrong outcome", stage: "title_abstract", position: 1 },
];

function routes(extra: Record<string, unknown> = {}) {
  return {
    ...signedIn,
    ...projectRoutes(),
    [`GET ${base}/exclusion-reasons`]: REASONS,
    [`GET ${base}/screening/queue`]: (request: Request) => {
      const held = new URL(request.url).searchParams.getAll("exclude");
      // The first page, then nothing more: enough to screen three records.
      return { items: held.length ? [] : [item(1), item(2), item(3)] };
    },
    [`PUT ${base}/records/r1/decision`]: async (request: Request) => ({
      record_id: "r1",
      stage: "title_abstract",
      decision: { ...((await request.json()) as object), updated_at: "2026-09-23T10:00:00Z" },
    }),
    ...extra,
  };
}

describe("screening", () => {
  test("a decision shows the next record at once and sends the time spent", async () => {
    let answer: (response: Response) => void = () => undefined;
    const server = mockApi(
      routes({
        // The server is slow to answer; the screen must not wait for it.
        [`PUT ${base}/records/r1/decision`]: () =>
          new Promise<Response>((resolve) => {
            answer = resolve;
          }),
      }),
    );
    const user = userEvent.setup();
    renderApp(page);

    expect(await screen.findByRole("heading", { name: /study 1/ })).toBeVisible();
    await user.keyboard("i");
    expect(await screen.findByRole("heading", { name: /study 2/ })).toBeVisible();

    const sent = server.calls(`PUT ${base}/records/r1/decision`)[0];
    const body = (await sent?.json()) as { decision: string; stage: string; time_spent_ms: number };
    expect(body.decision).toBe("include");
    expect(body.stage).toBe("title_abstract");
    expect(body.time_spent_ms).toBeGreaterThanOrEqual(0);
    // Screen-reader users hear what happened and what is next (guide 14).
    expect(screen.getByText(/Included\. Next record: .*study 2/)).toBeInTheDocument();
    await act(async () => {
      answer(
        json({
          record_id: "r1",
          stage: "title_abstract",
          decision: {
            decision: "include",
            reason_ids: [],
            note: null,
            updated_at: "2026-09-23T10:00:00Z",
          },
        }),
      );
      await Promise.resolve();
    });
  });

  test("a required reason is asked for before an exclusion is sent", async () => {
    const withRule: Project = {
      ...PROJECT,
      settings: { ...PROJECT.settings, require_reason_on_exclude_ta: true },
    };
    mockApi(routes({ [`GET ${base}`]: withRule }));
    const user = userEvent.setup();
    renderApp(page);

    expect(await screen.findByRole("heading", { name: /study 1/ })).toBeVisible();
    expect(screen.getByText(/Exclusion reasons \(required\)/)).toBeVisible();
    await user.keyboard("e");
    expect(screen.getByRole("heading", { name: /study 1/ })).toBeVisible();
    expect(screen.getByText("Choose an exclusion reason, then exclude.")).toBeInTheDocument();

    // R turns on numbers, 2 picks the second reason, E excludes.
    await user.keyboard("r2e");
    expect(await screen.findByRole("heading", { name: /study 2/ })).toBeVisible();
  });

  test("a decision the server refuses puts the record back and says why", async () => {
    mockApi(
      routes({
        [`PUT ${base}/records/r1/decision`]: () =>
          problemResponse(409, {
            title: "Conflict",
            code: "conflict",
            detail: "Not in this stage.",
          }),
      }),
    );
    const user = userEvent.setup();
    renderApp(page);

    await screen.findByRole("heading", { name: /study 1/ });
    await user.click(screen.getByRole("button", { name: /Include/ }));
    expect(await screen.findByText("Not in this stage.")).toBeVisible();
    expect(screen.getByRole("heading", { name: /study 1/ })).toBeVisible();
  });

  test("Ctrl+Z takes the last decision back", async () => {
    const server = mockApi(
      routes({
        [`DELETE ${base}/records/r1/decision`]: {
          record_id: "r1",
          stage: "title_abstract",
          decision: null,
        },
      }),
    );
    const user = userEvent.setup();
    renderApp(page);

    await screen.findByRole("heading", { name: /study 1/ });
    await user.keyboard("m");
    await screen.findByRole("heading", { name: /study 2/ });
    await user.keyboard("{Control>}z{/Control}");
    expect(await screen.findByRole("heading", { name: /study 1/ })).toBeVisible();
    expect(server.calls(`DELETE ${base}/records/r1/decision`)).toHaveLength(1);
  });

  test("shortcuts do not fire while typing a note", async () => {
    const server = mockApi(routes());
    const user = userEvent.setup();
    renderApp(page);

    await screen.findByRole("heading", { name: /study 1/ });
    await user.type(screen.getByLabelText("New note"), "is this an RCT");
    expect(server.calls(`PUT ${base}/records/r1/decision`)).toHaveLength(0);
    expect(screen.getByRole("heading", { name: /study 1/ })).toBeVisible();
  });

  test("keywords are highlighted, and H switches it off", async () => {
    mockApi(
      routes({
        [`GET ${base}/keyword-groups`]: [
          {
            id: "g1",
            name: "Population",
            color: "green",
            kind: "include",
            keywords: [
              { id: "k1", group_id: "g1", term: "nurses", is_regex: false, whole_word: true },
            ],
          },
        ],
      }),
    );
    const user = userEvent.setup();
    const { container } = renderApp(page);

    await screen.findByRole("heading", { name: /study 1/ });
    expect(await screen.findByText("Nurses", { selector: "mark" })).toBeVisible();
    await user.keyboard("h");
    expect(container.querySelector("mark")).toBeNull();
  });

  test("a blinded reviewer is shown no one else's decision", async () => {
    mockApi(routes());
    renderApp(page);
    await screen.findByRole("heading", { name: /study 1/ });
    expect(screen.queryByRole("region", { name: "Other reviewers" })).toBeNull();
  });

  test("others' decisions are shown to someone allowed to see them", async () => {
    mockApi(
      routes({
        [`GET ${base}/screening/queue`]: {
          items: [
            item(1, {
              others: [
                {
                  user_id: "u2",
                  name: "Grace Hopper",
                  decision: "exclude",
                  reason_ids: ["why1"],
                  note: "Not nurses.",
                  updated_at: "2026-09-23T09:00:00Z",
                },
              ],
            }),
          ],
        },
      }),
    );
    renderApp(page);
    const others = within(await screen.findByRole("region", { name: "Other reviewers" }));
    expect(others.getByText(/Grace Hopper/)).toBeVisible();
    expect(others.getByText(/Wrong population/)).toBeVisible();
    expect(others.getByText(/Not nurses/)).toBeVisible();
  });

  test("the history lists my decisions and opens one again", async () => {
    mockApi(
      routes({
        [`GET ${base}/my-history`]: {
          items: [
            {
              record_id: "r9",
              title: "An older record I excluded",
              year: 2019,
              decision: "exclude",
              reason_ids: [],
              updated_at: "2026-09-23T09:00:00Z",
            },
          ],
          next_cursor: null,
        },
        [`GET ${base}/screening/records/r9`]: item(9, {
          title: "An older record I excluded",
          my_decision: {
            decision: "exclude",
            reason_ids: [],
            note: null,
            updated_at: "2026-09-23T09:00:00Z",
          },
        }),
      }),
    );
    const user = userEvent.setup();
    renderApp(page);

    await screen.findByRole("heading", { name: /study 1/ });
    await user.click(screen.getByRole("button", { name: /History/ }));
    await user.click(await screen.findByRole("button", { name: /An older record I excluded/ }));
    expect(
      await screen.findByRole("heading", { name: "An older record I excluded" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: /Exclude/, pressed: true })).toBeVisible();
  });

  test("? lists the keyboard shortcuts", async () => {
    mockApi(routes());
    const user = userEvent.setup();
    renderApp(page);
    await screen.findByRole("heading", { name: /study 1/ });
    await user.keyboard("?");
    const help = within(await screen.findByRole("dialog"));
    expect(help.getByText("Undo the last decision")).toBeVisible();
  });

  test("when everything is screened, the page says so", async () => {
    mockApi(routes({ [`GET ${base}/screening/queue`]: { items: [] } }));
    renderApp(page);
    expect(await screen.findByText("Nothing left for you to screen here.")).toBeVisible();
  });

  test("on a phone the record is a card with the buttons below it", async () => {
    setMedia({ mobile: true });
    mockApi(routes());
    renderApp(page);
    expect(await screen.findByText(/swipe up here for maybe/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reasons, labels, notes/ })).toBeVisible();
    expect(screen.getAllByRole("group", { name: "Decision" })).toHaveLength(1);
  });

  test("a viewer is told they do not screen", async () => {
    const asViewer: Project = {
      ...PROJECT,
      membership: { ...PROJECT.membership, role: "viewer" },
      permissions: ["view", "export"],
    };
    mockApi({ ...signedIn, ...projectRoutes(asViewer) });
    renderApp(page);
    expect(await screen.findByText(/Viewers do not screen/)).toBeVisible();
  });
});
