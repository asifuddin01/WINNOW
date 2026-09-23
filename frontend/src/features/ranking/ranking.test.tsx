import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { foundAfter, ticks } from "@/features/ranking/curve";
import { PROJECT, RANKING_STATUS, USER, mockApi, projectRoutes } from "@/test/api";
import { renderApp } from "@/test/render-app";

const signedIn = { "GET /api/v1/auth/me": USER };
const base = `/api/v1/projects/${PROJECT.id}`;
const withRecords = {
  [`GET ${base}/records/facets`]: {
    title_abstract: [{ value: "pending", label: "pending", count: 400 }],
    full_text: [],
    years: [],
    imports: [],
    duplicates: 0,
    total: 400,
  },
};
const CURVE = {
  stage: "title_abstract",
  total: 400,
  mine: { screened: 120, found_at: [3, 8, 20, 41] },
  team: { screened: 200, found_at: [3, 8, 11, 20, 41, 90] },
};
const MODEL = {
  trained_at: new Date(Date.now() - 3 * 60_000).toISOString(),
  n_labeled: 180,
  n_included: 12,
  auc: 0.91,
  scored: 220,
};

describe("the ranking panel", () => {
  test("before the first model it says what the model waits for", async () => {
    mockApi({
      ...signedIn,
      ...projectRoutes(),
      ...withRecords,
      [`GET ${base}/ranking/status`]: { ...RANKING_STATUS, have_included: 3, have_excluded: 9 },
    });
    renderApp(`/p/${PROJECT.id}`);
    expect(await screen.findByText(/first model is trained once the team has decided 5/)).toBe(
      screen.getByText(/So far: 3 of 5 relevant, 5 of 5 excluded/),
    );
    expect(screen.getByText("The recall curve starts with the first decision.")).toBeVisible();
  });

  test("with a model it says what it learnt from, and retrains on demand", async () => {
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(),
      ...withRecords,
      [`GET ${base}/ranking/status`]: { ...RANKING_STATUS, model: MODEL },
      [`GET ${base}/ranking/curve`]: CURVE,
      [`POST ${base}/ranking/train`]: { queued: true },
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}`);

    expect(await screen.findByText(/Trained 3 minutes ago on 180 decided records/)).toBeVisible();
    expect(screen.getByText(/Cross-validated AUC 0.91/)).toBeVisible();
    expect(screen.getByText(/one record in 20 is picked at random/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Retrain now" }));
    expect(await screen.findByText(/Retraining/)).toBeVisible();
    expect(server.calls(`POST ${base}/ranking/train`)).toHaveLength(1);
  });

  test("a reviewer screening blind is not told the team's numbers", async () => {
    mockApi({
      ...signedIn,
      ...projectRoutes(),
      ...withRecords,
      [`GET ${base}/ranking/status`]: {
        ...RANKING_STATUS,
        model: { ...MODEL, n_labeled: null, n_included: null, auc: null },
      },
    });
    renderApp(`/p/${PROJECT.id}`);
    expect(await screen.findByText(/on the team's decisions/)).toBeVisible();
    expect(screen.queryByText(/AUC/)).toBeNull();
  });

  test("with ranking off it points to the setting", async () => {
    mockApi({
      ...signedIn,
      ...projectRoutes(),
      ...withRecords,
      [`GET ${base}/ranking/status`]: { ...RANKING_STATUS, enabled: false },
    });
    renderApp(`/p/${PROJECT.id}`);
    expect(await screen.findByText(/Ranking is off for this review/)).toBeVisible();
    expect(screen.getByRole("link", { name: /Turn ranking on/ })).toHaveAttribute(
      "href",
      `/p/${PROJECT.id}/settings/screening`,
    );
    expect(screen.queryByRole("button", { name: "Retrain now" })).toBeNull();
  });
});

describe("the recall curve", () => {
  test("has a legend, a keyboard readout and a table", async () => {
    mockApi({
      ...signedIn,
      ...projectRoutes(),
      ...withRecords,
      [`GET ${base}/ranking/status`]: { ...RANKING_STATUS, model: MODEL },
      [`GET ${base}/ranking/curve`]: CURVE,
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}`);

    const chart = await screen.findByRole("img", { name: /Recall curve/ });
    expect(chart).toHaveAccessibleName(
      "Recall curve. Team: 6 relevant in 200 screened; You: 4 relevant in 120 screened. 400 records in the review.",
    );
    const figure = chart.closest("figure");
    if (!figure) throw new Error("The chart is not in a figure.");
    const legend = within(figure);
    expect(legend.getByText(/Same finds at an even pace/)).toBeVisible();

    const plot = within(chart.parentElement ?? figure);
    chart.focus();
    expect(await plot.findByRole("status")).toHaveTextContent("After 200 screened");
    fireEvent.keyDown(chart, { key: "ArrowLeft" });
    fireEvent.keyDown(chart, { key: "ArrowLeft" });
    expect(plot.getByRole("status")).toHaveTextContent("After 196 screened");

    await user.click(legend.getByText("Show as a table"));
    const table = legend.getByRole("table");
    // At 200 screened the team had found 6; you had screened only 120 by then.
    expect(within(table).getAllByRole("row").at(-1)).toHaveTextContent("2006—");
  });

  test("counts and ticks are worked out exactly", () => {
    const curve = { screened: 50, found_at: [2, 5, 5, 30] };
    expect(foundAfter(curve, 1)).toBe(0);
    expect(foundAfter(curve, 5)).toBe(3);
    expect(foundAfter(curve, 50)).toBe(4);
    expect(ticks(0)).toEqual([0]);
    expect(ticks(1240)).toEqual([0, 500, 1000, 1500]);
  });
});

describe("the stopping-rule helper", () => {
  const page = `/p/${PROJECT.id}/screen/ta`;
  const queue = {
    [`GET ${base}/screening/queue`]: {
      items: [
        {
          id: "r1",
          title: "A record",
          authors: [],
          year: 2020,
          journal: null,
          volume: null,
          issue: null,
          pages: null,
          doi: null,
          pmid: null,
          url: null,
          abstract: null,
          keywords: [],
          publication_type: [],
          relevance_score: 0.1,
          my_decision: null,
          labels: [],
          notes: [],
          others: null,
        },
      ],
    },
  };

  test("says so after a long run of excludes, and can be put away", async () => {
    mockApi({
      ...signedIn,
      ...projectRoutes(),
      ...queue,
      [`GET ${base}/screening/stopping`]: {
        stage: "title_abstract",
        rule: "consecutive_excludes",
        threshold: 200,
        in_a_row: 214,
        remaining: 3120,
        estimate: { expected: 1.4, low: 0, high: 3 },
      },
    });
    const user = userEvent.setup();
    renderApp(page);

    const helper = await screen.findByRole("region", {
      name: "You have excluded 214 records in a row",
    });
    expect(screen.getAllByRole("region", { name: /in a row/ })).toHaveLength(1);
    expect(helper).toHaveTextContent("about 1 (likely 0–3)");
    expect(helper).toHaveTextContent("Winnow never stops screening for you");
    await user.click(within(helper).getByRole("button", { name: "Keep screening" }));
    expect(screen.queryByRole("region", { name: /in a row/ })).toBeNull();
  });

  test("the relevance order says one record in twenty is random", async () => {
    mockApi({ ...signedIn, ...projectRoutes(), ...queue });
    renderApp(page);
    expect(await screen.findByText(/One record in 20 is picked at random/)).toBeInTheDocument();
  });
});
