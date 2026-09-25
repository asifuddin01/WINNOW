import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { PROJECT, USER, mockApi, projectRoutes, summaryOf } from "@/test/api";
import { renderApp } from "@/test/render-app";

const base = `/api/v1/projects/${PROJECT.id}`;
const RID = "00000000-0000-4000-8000-000000000001";
const OTHER = {
  ...PROJECT,
  id: "0192f0c1-0000-7000-8000-00000000bbb2",
  title: "Caffeine and alertness",
};

const RECORD = {
  id: RID,
  title: "Melatonin for night nurses",
  authors: ["Okafor, Ngozi"],
  year: 2018,
  journal: "Sleep Medicine",
  doi: "10.1000/mel.1",
  pmid: null,
  ta_final: "included",
  ft_final: "pending",
  is_duplicate: false,
  relevance_score: null,
  import_batch_id: null,
  created_at: "2026-09-23T09:00:00Z",
};

function routes(extra: Record<string, unknown> = {}) {
  return {
    "GET /api/v1/auth/me": USER,
    ...projectRoutes(),
    "GET /api/v1/projects": { items: [summaryOf(PROJECT), summaryOf(OTHER)], next_cursor: null },
    ...extra,
  };
}

const palette = () => screen.findByRole("combobox", { name: /Search pages, reviews, records/ });

describe("command palette", () => {
  test("Ctrl+K opens it; typing narrows it; the arrows and Enter go there", async () => {
    mockApi(routes());
    const user = userEvent.setup();
    const { router } = renderApp(`/p/${PROJECT.id}`);
    await screen.findByRole("heading", { name: PROJECT.title });

    await user.keyboard("{Control>}k{/Control}");
    const input = await palette();
    const list = screen.getByRole("listbox", { name: "Results" });
    expect(within(list).getByRole("group", { name: "Actions" })).toBeVisible();
    expect(within(list).getByRole("option", { name: /Caffeine and alertness/ })).toBeVisible();

    await user.type(input, "statis");
    const options = within(list).getAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual([`Report: Statistics${PROJECT.title}`]);
    expect(options[0]).toHaveAttribute("aria-selected", "true");
    expect(input).toHaveAttribute("aria-activedescendant", options[0]?.id);
    await user.keyboard("{Enter}");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/p/${PROJECT.id}/report/stats`);
    });
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  test("a record found by its title or DOI opens in the records table", async () => {
    const server = mockApi(
      routes({
        [`GET ${base}/records`]: (request: Request) =>
          new URL(request.url).searchParams.get("limit") === "8"
            ? { items: [RECORD], next_cursor: null, total: 1, total_is_exact: true }
            : { items: [], next_cursor: null, total: 0, total_is_exact: true },
        [`GET ${base}/records/${RID}`]: {
          ...RECORD,
          abstract: "About sleep.",
          volume: null,
          issue: null,
          pages: null,
          pmcid: null,
          isbn: null,
          url: null,
          keywords: [],
          language: null,
          publication_type: [],
          duplicate_of: null,
          raw: {},
          source: null,
        },
      }),
    );
    const user = userEvent.setup();
    const { router } = renderApp(`/p/${PROJECT.id}`);
    await screen.findByRole("heading", { name: PROJECT.title });

    await user.click(screen.getByRole("button", { name: /Search or jump to/ }));
    await user.type(await palette(), "10.1000/mel.1");
    const found = await screen.findByRole("option", { name: /Melatonin for night nurses/ });
    expect(found).toHaveTextContent("Okafor · 2018 · 10.1000/mel.1");
    const searched = server.calls(`GET ${base}/records`).at(-1);
    expect(new URL(searched?.url ?? "").searchParams.get("q")).toBe("10.1000/mel.1");
    await user.click(found);
    await waitFor(() => {
      expect(router.state.location.search).toEqual({ record: RID });
    });
    expect(await screen.findByText("About sleep.")).toBeVisible();
  });

  test("moving through results wraps; Escape closes; actions run", async () => {
    mockApi(routes());
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}`);
    await screen.findByRole("heading", { name: PROJECT.title });

    await user.keyboard("{Meta>}k{/Meta}");
    await palette();
    const options = within(screen.getByRole("listbox")).getAllByRole("option");
    await user.keyboard("{ArrowUp}");
    expect(options.at(-1)).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowDown}");
    expect(options[0]).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{End}");
    expect(options.at(-1)).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Home}{ArrowDown}");
    expect(options[1]).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("combobox")).toBeNull();

    await user.keyboard("{Control>}k{/Control}");
    await user.type(await palette(), "dark theme");
    await user.keyboard("{Enter}");
    await waitFor(() => {
      expect(document.documentElement.classList.contains("dark")).toBe(true);
    });

    await user.keyboard("{Control>}k{/Control}");
    await user.type(await palette(), "nothing like this");
    expect(within(screen.getByRole("dialog")).getByRole("status")).toHaveTextContent(
      "Nothing matches.",
    );
  });

  test("outside a review: pages, reviews and actions, but no record search", async () => {
    mockApi(routes());
    const user = userEvent.setup();
    const { router } = renderApp("/");
    await screen.findByRole("heading", { name: "My reviews" });

    await user.keyboard("{Control>}k{/Control}");
    const input = await palette();
    expect(input).toHaveAttribute("placeholder", "Type a page, a review or an action…");
    await user.type(input, "caffeine");
    await user.keyboard("{Enter}");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/p/${OTHER.id}`);
    });
  });
});
