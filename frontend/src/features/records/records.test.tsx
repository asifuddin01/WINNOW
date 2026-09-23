import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { PROJECT, USER, mockApi, projectRoutes } from "@/test/api";
import { renderApp } from "@/test/render-app";

const signedIn = { "GET /api/v1/auth/me": USER };
const base = `/api/v1/projects/${PROJECT.id}`;

function record(index: number, overrides: Record<string, unknown> = {}) {
  return {
    id: `r${index}`,
    title: `Shift work and sleep, study ${index}`,
    authors: ["Smith, Jane A", "Chowdhury, Sara"],
    year: 2019 + (index % 3),
    journal: "Journal of Advanced Nursing",
    doi: `10.1000/jan.${index}`,
    pmid: `312345${index}`,
    ta_final: "pending",
    ft_final: "not_eligible",
    is_duplicate: false,
    relevance_score: null,
    import_batch_id: "b1",
    created_at: "2026-09-23T09:00:00Z",
    ...overrides,
  };
}

const PAGE = {
  items: [record(1), record(2), record(3)],
  next_cursor: null,
  total: 3,
  total_is_exact: true,
};

const FACETS = {
  title_abstract: [
    { value: "pending", label: "pending", count: 3 },
    { value: "included", label: "included", count: 1 },
  ],
  full_text: [],
  years: [
    { value: "2019", label: "2019", count: 2 },
    { value: "2020", label: "2020", count: 1 },
  ],
  imports: [{ value: "b1", label: "PubMed 2026-09-23", count: 3 }],
  duplicates: 2,
  total: 4,
};

const DETAIL = {
  ...record(1),
  abstract: "AIM: to examine whether rotating night shifts affect sleep quality.",
  volume: "75",
  issue: "4",
  pages: "812-824",
  pmcid: null,
  isbn: null,
  url: "https://example.org/a",
  keywords: ["nurses", "shift work"],
  language: "eng",
  publication_type: ["Journal Article"],
  duplicate_of: null,
  raw: {},
  source: "PubMed 2026-09-23",
};

const routes = {
  ...signedIn,
  ...projectRoutes(),
  [`GET ${base}/records`]: PAGE,
  [`GET ${base}/records/facets`]: FACETS,
  [`GET ${base}/records/r1`]: DETAIL,
};

describe("the records table", () => {
  test("lists records with their counts and opens one", async () => {
    mockApi(routes);
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/records`);

    expect(await screen.findByText("3 records")).toBeVisible();
    await user.click(screen.getByRole("button", { name: /study 1/ }));

    const detail = within(await screen.findByRole("article"));
    expect(detail.getByRole("heading", { name: /study 1/ })).toBeVisible();
    expect(detail.getByText(/rotating night shifts affect sleep/)).toBeVisible();
    expect(detail.getByRole("link", { name: "10.1000/jan.1" })).toHaveAttribute(
      "href",
      "https://doi.org/10.1000/jan.1",
    );
    expect(detail.getByText("PubMed 2026-09-23")).toBeVisible();
  });

  test("searching puts the query in the URL so the link can be shared", async () => {
    const server = mockApi(routes);
    const user = userEvent.setup();
    const { router } = renderApp(`/p/${PROJECT.id}/records`);

    await user.type(await screen.findByLabelText("Search"), 'author:smith "night shift"');
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(router.state.location.search).toEqual({ q: 'author:smith "night shift"' });
    const asked = server
      .calls(`GET ${base}/records`)
      .map((request) => new URL(request.url).searchParams.get("q"));
    expect(asked).toContain('author:smith "night shift"');
  });

  test("the filters ask for the status they count", async () => {
    const server = mockApi(routes);
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/records`);

    const filters = within(await screen.findByRole("navigation", { name: "Filters" }));
    expect(filters.getByRole("button", { name: /All records/ })).toBeVisible();
    await user.click(filters.getByRole("button", { name: /included/ }));

    const statuses = server
      .calls(`GET ${base}/records`)
      .map((request) => new URL(request.url).searchParams.get("status"));
    expect(statuses).toContain("included");
  });

  test("the order can be changed", async () => {
    const server = mockApi(routes);
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/records`);

    (await screen.findByLabelText("Order")).focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("option", { name: "Year, newest" }));

    const sorts = server
      .calls(`GET ${base}/records`)
      .map((request) => new URL(request.url).searchParams.get("sort"));
    expect(sorts).toContain("year");
  });

  test("the next page is fetched as the end of the list comes into view", async () => {
    const second = {
      items: [record(4), record(5)],
      next_cursor: null,
      total: 5,
      total_is_exact: true,
    };
    mockApi({
      ...routes,
      [`GET ${base}/records`]: (request: Request) =>
        new URL(request.url).searchParams.get("cursor")
          ? second
          : { ...PAGE, next_cursor: "c2", total: 5 },
    });
    renderApp(`/p/${PROJECT.id}/records`);

    // The virtualiser keeps eight rows beyond the last visible one, so reaching the end
    // of a short page asks for the next one without any scrolling.
    expect(await screen.findByText(/study 5/)).toBeVisible();
  });

  test("an empty result says so rather than showing nothing", async () => {
    mockApi({
      ...routes,
      [`GET ${base}/records`]: { items: [], next_cursor: null, total: 0, total_is_exact: true },
    });
    renderApp(`/p/${PROJECT.id}/records?q=kangaroo`);
    expect(await screen.findByText(/No records match/)).toBeVisible();
  });

  test("a filter from the URL is applied on the first load", async () => {
    const server = mockApi(routes);
    renderApp(`/p/${PROJECT.id}/records?status=included&sort=title`);

    expect(await screen.findByText("3 records")).toBeVisible();
    const request = server.calls(`GET ${base}/records`)[0];
    const params = new URL(request?.url ?? "https://x/").searchParams;
    expect(params.get("status")).toBe("included");
    expect(params.get("sort")).toBe("title");
  });
});
