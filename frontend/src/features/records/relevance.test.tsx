import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import type { Record as ReviewRecord, RecordDetail } from "@/api/records";
import { PROJECT, USER, mockApi, projectRoutes } from "@/test/api";
import { renderApp } from "@/test/render-app";

const base = `/api/v1/projects/${PROJECT.id}`;
const record: ReviewRecord = {
  id: "r1",
  title: "Shift work and sleep",
  authors: ["Smith, Jane A", "Chowdhury, Sara"],
  year: 2020,
  journal: "Journal of Advanced Nursing",
  doi: "10.1000/jan.1",
  pmid: "3123451",
  ta_final: "pending",
  ft_final: "not_eligible",
  is_duplicate: false,
  relevance_score: null,
  import_batch_id: "b1",
  created_at: "2026-09-23T09:00:00Z",
};
const detail: RecordDetail = {
  ...record,
  abstract: "Rotating night shifts and sleep quality in nurses.",
  volume: "75",
  issue: "4",
  pages: "812-824",
  pmcid: null,
  isbn: null,
  url: null,
  keywords: [],
  language: "eng",
  publication_type: ["Journal Article"],
  duplicate_of: null,
  raw: {},
  source: "PubMed",
};
const note = "The ranking model's estimate from this review's decisions.";
const percentages = [
  { score: 0.82, label: "Relevance 82%" },
  { score: 0.826, label: "Relevance 83%" },
  { score: 0, label: "Relevance 0%" },
];

function recordsApi(score: number | null = null) {
  return mockApi({
    "GET /api/v1/auth/me": USER,
    ...projectRoutes(),
    [`GET ${base}/records`]: {
      items: [{ ...record, relevance_score: score }],
      next_cursor: null,
      total: 1,
      total_is_exact: true,
    },
    [`GET ${base}/records/r1`]: { ...detail, relevance_score: score },
  });
}

describe("relevance on the Records page", () => {
  test("choosing relevance updates the URL and the records request", async () => {
    const server = recordsApi();
    const user = userEvent.setup();
    const { router } = renderApp(`/p/${PROJECT.id}/records`);

    (await screen.findByLabelText("Order")).focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("option", { name: "Relevance, highest first" }));

    await waitFor(() => {
      expect(router.state.location.search).toEqual({ sort: "relevance" });
      const sorts = server
        .calls(`GET ${base}/records`)
        .map((request) => new URL(request.url).searchParams.get("sort"));
      expect(sorts).toContain("relevance");
    });
    expect(screen.getByLabelText("Order")).toHaveTextContent("Relevance, highest first");
  });

  test("a shared relevance URL selects the order and requests it on first load", async () => {
    const server = recordsApi();
    renderApp(`/p/${PROJECT.id}/records?sort=relevance`);

    expect(await screen.findByText("1 record")).toBeVisible();
    expect(screen.getByLabelText("Order")).toHaveTextContent("Relevance, highest first");
    const request = server.calls(`GET ${base}/records`)[0];
    expect(request).toBeDefined();
    expect(new URL(request?.url ?? "https://example.org/").searchParams.get("sort")).toBe(
      "relevance",
    );
  });

  test.each(percentages)(
    "a row with score $score ends its metadata with $label",
    async ({ score, label }) => {
      recordsApi(score);
      renderApp(`/p/${PROJECT.id}/records`);

      const row = within(await screen.findByRole("button", { name: /Shift work and sleep/ }));
      expect(
        row.getByText(
          `Smith, Jane A; Chowdhury, Sara · 2020 · Journal of Advanced Nursing · ${label}`,
        ),
      ).toBeVisible();
    },
  );

  test("a row with a null score has no relevance text", async () => {
    recordsApi();
    renderApp(`/p/${PROJECT.id}/records`);

    const row = within(await screen.findByRole("button", { name: /Shift work and sleep/ }));
    expect(row.queryByText(/Relevance/)).not.toBeInTheDocument();
    expect(
      row.getByText("Smith, Jane A; Chowdhury, Sara · 2020 · Journal of Advanced Nursing"),
    ).toBeVisible();
  });

  test.each(percentages)(
    "the detail panel shows $label and explains the estimate",
    async ({ score, label }) => {
      recordsApi(score);
      const user = userEvent.setup();
      renderApp(`/p/${PROJECT.id}/records`);

      await user.click(await screen.findByRole("button", { name: /Shift work and sleep/ }));

      const panel = within(await screen.findByRole("article"));
      expect(panel.getByText(label)).toBeVisible();
      expect(panel.getByText(note)).toBeVisible();
    },
  );

  test("the detail panel omits the score and note when the score is null", async () => {
    recordsApi();
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/records`);

    await user.click(await screen.findByRole("button", { name: /Shift work and sleep/ }));

    const panel = within(await screen.findByRole("article"));
    expect(panel.getByRole("heading", { name: "Shift work and sleep" })).toBeVisible();
    expect(panel.queryByText(/Relevance/)).not.toBeInTheDocument();
    expect(panel.queryByText(note)).not.toBeInTheDocument();
  });
});
