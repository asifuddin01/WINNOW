import { act, fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { PROJECT, USER, mockApi, problemResponse, projectRoutes } from "@/test/api";
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
    volume: "12",
    issue: "3",
    pages: "1-9",
    doi: null,
    pmid: `3100000${index}`,
    url: null,
    abstract: `Nurses slept less in study ${index}.`,
    keywords: ["sleep", "nurses"],
    publication_type: ["Journal Article"],
    relevance_score: 0.82,
    my_decision: null,
    labels: [],
    notes: [],
    others: null,
    ...overrides,
  };
}

const LABELS = [{ id: "l1", name: "RCT", color: "blue" }];

function routes(extra: Record<string, unknown> = {}) {
  return {
    ...signedIn,
    ...projectRoutes(),
    [`GET ${base}/labels`]: LABELS,
    [`GET ${base}/keyword-groups`]: [
      {
        id: "g1",
        name: "Population",
        color: "green",
        kind: "include",
        keywords: [{ id: "k1", group_id: "g1", term: "nurses", is_regex: false, whole_word: true }],
      },
    ],
    [`GET ${base}/screening/queue`]: (request: Request) => {
      const url = new URL(request.url);
      if (url.searchParams.getAll("exclude").length) return { items: [] };
      if (url.searchParams.get("q") === "nothing") return { items: [] };
      return { items: [item(1), item(2), item(3)] };
    },
    [`PUT ${base}/records/r1/decision`]: {
      record_id: "r1",
      stage: "title_abstract",
      decision: {
        decision: "include",
        reason_ids: [],
        note: null,
        updated_at: "2026-09-23T10:00:00Z",
      },
    },
    ...extra,
  };
}

describe("moving through the queue", () => {
  test("J and K step forward and back without deciding", async () => {
    const server = mockApi(routes());
    const user = userEvent.setup();
    renderApp(page);

    await screen.findByRole("heading", { name: /study 1/ });
    await user.keyboard("j");
    expect(await screen.findByRole("heading", { name: /study 2/ })).toBeVisible();
    await user.keyboard("{ArrowRight}");
    expect(await screen.findByRole("heading", { name: /study 3/ })).toBeVisible();
    await user.keyboard("k");
    expect(await screen.findByRole("heading", { name: /study 2/ })).toBeVisible();
    await user.click(screen.getByRole("button", { name: /Previous/ }));
    expect(await screen.findByRole("heading", { name: /study 1/ })).toBeVisible();
    expect(server.calls(`PUT ${base}/records/r1/decision`)).toHaveLength(0);
  });

  test("focus mode keeps only the record and the decision", async () => {
    mockApi(routes());
    const user = userEvent.setup();
    renderApp(page);

    await screen.findByRole("heading", { name: /study 1/ });
    expect(screen.getByRole("complementary", { name: "Your decision" })).toBeVisible();
    await user.keyboard("f");
    expect(screen.queryByRole("complementary", { name: "Your decision" })).toBeNull();
    expect(screen.getByRole("group", { name: "Decision" })).toBeVisible();
    // R shows the reasons under the buttons in focus mode.
    expect(screen.queryByRole("list", { name: "Exclusion reasons" })).toBeNull();
    await user.keyboard("r");
    expect(screen.getByText(/no exclusion reasons/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: /Focus/ }));
    expect(screen.getByRole("complementary", { name: "Your decision" })).toBeVisible();
  });

  test("the search goes into the URL, and an empty result offers to clear it", async () => {
    mockApi(routes());
    const user = userEvent.setup();
    const { router } = renderApp(page);

    await screen.findByRole("heading", { name: /study 1/ });
    await user.keyboard("/");
    const box = screen.getByRole("textbox", { name: /Search/ });
    expect(box).toHaveFocus();
    await user.type(box, "nothing");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(router.state.location.search).toEqual({ q: "nothing" });
    await user.click(await screen.findByRole("button", { name: "Clear the search" }));
    expect(router.state.location.search).toEqual({});
    expect(await screen.findByRole("heading", { name: /study 1/ })).toBeVisible();
  });

  test("the order can be changed", async () => {
    mockApi(routes());
    const user = userEvent.setup();
    const { router } = renderApp(page);

    await screen.findByRole("heading", { name: /study 1/ });
    screen.getByLabelText("Order").focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("option", { name: "Year, newest" }));
    expect(router.state.location.search).toEqual({ sort: "year" });
  });

  test("a keyword group can be switched off on its own", async () => {
    mockApi(routes());
    const user = userEvent.setup();
    const { container } = renderApp(page);

    await screen.findByRole("heading", { name: /study 1/ });
    expect(container.querySelector("mark")).not.toBeNull();
    await user.click(screen.getByRole("button", { name: /Population/, pressed: true }));
    expect(container.querySelector("mark")).toBeNull();
  });
});

describe("labels and notes", () => {
  test("a label is applied at once, and put back if the server refuses", async () => {
    const server = mockApi(
      routes({
        [`PUT ${base}/records/r1/labels`]: () =>
          problemResponse(422, { title: "Unprocessable", detail: "No such label." }),
      }),
    );
    const user = userEvent.setup();
    renderApp(page);

    await screen.findByRole("heading", { name: /study 1/ });
    const labels = within(screen.getByRole("list", { name: "Labels" }));
    await user.click(labels.getByRole("button", { name: "RCT" }));
    expect(await screen.findByText("No such label.")).toBeVisible();
    expect(labels.getByRole("button", { name: "RCT", pressed: false })).toBeVisible();
    expect(await server.calls(`PUT ${base}/records/r1/labels`)[0]?.json()).toEqual({
      label_ids: ["l1"],
    });
  });

  test("a team note is added under the record", async () => {
    const server = mockApi(
      routes({
        [`POST ${base}/records/r1/notes`]: {
          id: "n1",
          body: "Check the population.",
          visibility: "team",
          author: USER.name,
          mine: true,
          created_at: "2026-09-23T10:00:00Z",
        },
      }),
    );
    const user = userEvent.setup();
    renderApp(page);

    await screen.findByRole("heading", { name: /study 1/ });
    await user.type(screen.getByLabelText("New note"), "Check the population.");
    await user.click(screen.getByRole("radio", { name: "Team" }));
    await user.click(screen.getByRole("button", { name: "Add note" }));
    expect(await screen.findByText("Check the population.", { selector: "span" })).toBeVisible();
    expect(await server.calls(`POST ${base}/records/r1/notes`)[0]?.json()).toEqual({
      body: "Check the population.",
      visibility: "team",
    });
    expect(screen.getByLabelText("New note")).toHaveValue("");
  });
});

describe("decisions that cannot be sent", () => {
  test("with no connection they wait in memory and go when it is back", async () => {
    let online = false;
    const server = mockApi(
      routes({
        [`PUT ${base}/records/r1/decision`]: () => {
          if (!online) throw new TypeError("Failed to fetch");
          return {
            record_id: "r1",
            stage: "title_abstract",
            decision: {
              decision: "exclude",
              reason_ids: [],
              note: null,
              updated_at: "2026-09-23T10:00:00Z",
            },
          };
        },
      }),
    );
    const user = userEvent.setup();
    renderApp(page);

    await screen.findByRole("heading", { name: /study 1/ });
    await user.keyboard("e");
    expect(await screen.findByText(/1 decision waiting to sync/)).toBeVisible();
    expect(screen.getByRole("heading", { name: /study 2/ })).toBeVisible();
    // Leaving the page now would lose it, so the browser is asked to check first.
    const leaving = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(leaving);
    expect(leaving.defaultPrevented).toBe(true);

    online = true;
    await act(async () => {
      window.dispatchEvent(new Event("online"));
      await Promise.resolve();
    });
    await vi.waitFor(() => {
      expect(screen.queryByText(/waiting to sync/)).toBeNull();
    });
    expect(server.calls(`PUT ${base}/records/r1/decision`).length).toBeGreaterThanOrEqual(2);
  });
});

describe("on a phone", () => {
  test("swiping right includes, left excludes, and up on the handle is maybe", async () => {
    setMedia({ mobile: true });
    const server = mockApi(
      routes({
        [`PUT ${base}/records/r2/decision`]: {
          record_id: "r2",
          stage: "title_abstract",
          decision: {
            decision: "exclude",
            reason_ids: [],
            note: null,
            updated_at: "2026-09-23T10:00:00Z",
          },
        },
        [`PUT ${base}/records/r3/decision`]: {
          record_id: "r3",
          stage: "title_abstract",
          decision: {
            decision: "maybe",
            reason_ids: [],
            note: null,
            updated_at: "2026-09-23T10:00:00Z",
          },
        },
      }),
    );
    renderApp(page);

    const heading = await screen.findByRole("heading", { name: /study 1/ });
    const card = heading.closest<HTMLElement>("[style]");
    if (!card) throw new Error("The record is not on a card.");
    const swipe = (target: HTMLElement, dx: number, dy: number) => {
      fireEvent.pointerDown(target, { pointerType: "touch", clientX: 100, clientY: 300 });
      fireEvent.pointerMove(card, { pointerType: "touch", clientX: 100 + dx, clientY: 300 + dy });
      fireEvent.pointerUp(card, { pointerType: "touch", clientX: 100 + dx, clientY: 300 + dy });
    };

    swipe(card, 160, 0);
    await screen.findByRole("heading", { name: /study 2/ });
    swipe(card, -160, 0);
    await screen.findByRole("heading", { name: /study 3/ });
    swipe(screen.getByText(/swipe up here for maybe/), 0, -160);
    await vi.waitFor(() => {
      expect(server.calls(`PUT ${base}/records/r3/decision`)).toHaveLength(1);
    });
    const decisions = await Promise.all(
      ["r1", "r2", "r3"].map(async (id) => {
        const body = (await server.calls(`PUT ${base}/records/${id}/decision`)[0]?.json()) as {
          decision: string;
        };
        return body.decision;
      }),
    );
    expect(decisions).toEqual(["include", "exclude", "maybe"]);
  });

  test("a mouse drag is not a swipe, and a short one does nothing", async () => {
    setMedia({ mobile: true });
    const server = mockApi(routes());
    renderApp(page);

    const heading = await screen.findByRole("heading", { name: /study 1/ });
    const card = heading.closest<HTMLElement>("[style]");
    if (!card) throw new Error("The record is not on a card.");
    fireEvent.pointerDown(card, { pointerType: "mouse", clientX: 100, clientY: 300 });
    fireEvent.pointerMove(card, { pointerType: "mouse", clientX: 300, clientY: 300 });
    fireEvent.pointerUp(card, { pointerType: "mouse", clientX: 300, clientY: 300 });
    fireEvent.pointerDown(card, { pointerType: "touch", clientX: 100, clientY: 300 });
    fireEvent.pointerMove(card, { pointerType: "touch", clientX: 140, clientY: 300 });
    fireEvent.pointerUp(card, { pointerType: "touch", clientX: 140, clientY: 300 });
    expect(screen.getByRole("heading", { name: /study 1/ })).toBeVisible();
    expect(server.calls(`PUT ${base}/records/r1/decision`)).toHaveLength(0);
  });

  test("reasons, labels and notes open in a sheet", async () => {
    setMedia({ mobile: true });
    mockApi(routes());
    const user = userEvent.setup();
    renderApp(page);

    await screen.findByRole("heading", { name: /study 1/ });
    await user.click(screen.getByRole("button", { name: /Reasons, labels, notes/ }));
    const sheet = within(await screen.findByRole("dialog"));
    expect(sheet.getByRole("list", { name: "Labels" })).toBeVisible();
    expect(sheet.getByLabelText("New note")).toBeVisible();
  });
});

describe("time on a record", () => {
  test("time while the tab is hidden does not count", async () => {
    const server = mockApi(routes());
    const user = userEvent.setup();
    renderApp(page);
    await screen.findByRole("heading", { name: /study 1/ });

    let now = 1_000;
    const clock = vi.spyOn(performance, "now").mockImplementation(() => now);
    const hidden = vi.spyOn(document, "hidden", "get");
    // Visible for 4 s, hidden for an hour, visible for 2 s more.
    hidden.mockReturnValue(false);
    now += 4_000;
    hidden.mockReturnValue(true);
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    now += 3_600_000;
    hidden.mockReturnValue(false);
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    now += 2_000;
    await user.keyboard("i");

    const body = (await server.calls(`PUT ${base}/records/r1/decision`)[0]?.json()) as {
      time_spent_ms: number;
    };
    expect(body.time_spent_ms).toBeLessThan(60_000);
    clock.mockRestore();
    hidden.mockRestore();
  });
});
