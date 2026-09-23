import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import type { Project } from "@/api/projects";
import { PROJECT, USER, mockApi, projectRoutes } from "@/test/api";
import { renderApp } from "@/test/render-app";

const signedIn = { "GET /api/v1/auth/me": USER };
const base = `/api/v1/projects/${PROJECT.id}`;

function member(index: number, overrides: Record<string, unknown> = {}) {
  return {
    id: `r${index}`,
    is_primary: index === 1,
    title: "Rotating night shifts and sleep quality in nurses",
    authors: ["Smith, Jane A", "Chowdhury, Sara"],
    year: 2019,
    journal: "Journal of Advanced Nursing",
    volume: "75",
    issue: "4",
    pages: "812-824",
    doi: "10.1111/jan.13894",
    pmid: "31234567",
    abstract: "AIM: to examine whether rotating night shifts affect sleep quality.",
    url: null,
    keywords: [],
    publication_type: [],
    is_duplicate: false,
    created_at: "2026-09-23T09:00:00Z",
    source: "PubMed 2026-09-23",
    database_name: "PubMed",
    ...overrides,
  };
}

const CLUSTER = {
  id: "c1",
  status: "pending",
  score: 0.94,
  auto_resolvable: false,
  created_at: "2026-09-23T09:00:00Z",
  members: [
    member(1),
    member(2, {
      is_primary: false,
      journal: "J Adv Nurs",
      authors: ["Smith, J."],
      doi: null,
      pmid: null,
      abstract: null,
      database_name: "Scopus",
      source: "Scopus 2026-09-23",
    }),
  ],
};

const SUMMARY = { pending: 1, certain: 0, resolved: 0, ignored: 0, duplicates: 0 };

const routes = {
  ...signedIn,
  ...projectRoutes(),
  [`GET ${base}/dedup/summary`]: SUMMARY,
  [`GET ${base}/dedup/clusters`]: [CLUSTER],
};

describe("the duplicates screen", () => {
  test("shows the copies side by side and marks what differs", async () => {
    mockApi(routes);
    renderApp(`/p/${PROJECT.id}/duplicates`);

    const card = within(await screen.findByRole("article"));
    expect(card.getByText(/94% alike/)).toBeVisible();
    // The fields the two copies disagree about are named, so the reviewer knows where
    // to look before reading the table.
    expect(card.getByText(/differ on .*journal/)).toBeVisible();
    // The cell also tells a screen reader that this is one of the fields that differ.
    expect(card.getByRole("cell", { name: /J Adv Nurs\(differs\)/ })).toBeVisible();
    expect(card.getByText("PubMed")).toBeVisible();
    expect(card.getByText("Scopus")).toBeVisible();
    expect(await screen.findByText("Waiting for you")).toBeVisible();
  });

  test("merging keeps the copy the reviewer chose", async () => {
    const server = mockApi({
      ...routes,
      [`POST ${base}/dedup/clusters/c1/merge`]: {
        cluster_id: "c1",
        primary_id: "r2",
        merged: 1,
        clusters: 1,
      },
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/duplicates`);

    const card = within(await screen.findByRole("article"));
    await user.click(card.getByRole("radio", { name: /Keep the copy from Scopus/ }));
    await user.click(card.getByRole("button", { name: /Merge, keeping the chosen copy/ }));

    const call = server.calls(`POST ${base}/dedup/clusters/c1/merge`)[0];
    expect(await call?.json()).toEqual({ primary_id: "r2" });
  });

  test("Winnow suggests the fullest copy, and says so", async () => {
    mockApi(routes);
    renderApp(`/p/${PROJECT.id}/duplicates`);

    const card = within(await screen.findByRole("article"));
    const suggested = card.getAllByRole("radio")[0];
    expect(suggested).toBeChecked();
    expect(card.getByText(/Winnow suggests it/)).toBeVisible();
  });

  test("not duplicates keeps them apart", async () => {
    const server = mockApi({
      ...routes,
      [`POST ${base}/dedup/clusters/c1/ignore`]: { ...CLUSTER, status: "ignored" },
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/duplicates`);

    await user.click(await screen.findByRole("button", { name: "Not duplicates" }));
    expect(server.calls(`POST ${base}/dedup/clusters/c1/ignore`)).toHaveLength(1);
  });

  test("the certain groups can be merged in one go", async () => {
    const server = mockApi({
      ...routes,
      [`GET ${base}/dedup/summary`]: { ...SUMMARY, pending: 12, certain: 9 },
      [`POST ${base}/dedup/auto-resolve`]: {
        cluster_id: null,
        primary_id: null,
        merged: 9,
        clusters: 9,
      },
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/duplicates`);

    expect(await screen.findByText(/9 groups share a DOI or PubMed id/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Merge them all" }));

    expect(await server.calls(`POST ${base}/dedup/auto-resolve`)[0]?.json()).toEqual({
      min_score: 0.98,
    });
  });

  test("looking again is one button, and the worker does the work", async () => {
    const server = mockApi({ ...routes, [`POST ${base}/dedup/run`]: { job_id: "j1" } });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/duplicates`);

    await user.click(await screen.findByRole("button", { name: "Find duplicates" }));
    expect(server.calls(`POST ${base}/dedup/run`)).toHaveLength(1);
    expect(await screen.findByRole("button", { name: "Looking…" })).toBeDisabled();
  });

  test("nothing to decide says what has already been merged", async () => {
    mockApi({
      ...routes,
      [`GET ${base}/dedup/summary`]: { ...SUMMARY, pending: 0, resolved: 4, duplicates: 6 },
      [`GET ${base}/dedup/clusters`]: [],
    });
    renderApp(`/p/${PROJECT.id}/duplicates`);
    expect(await screen.findByText(/6 duplicates have been merged/)).toBeVisible();
  });

  test("a reviewer sees the groups but decides nothing", async () => {
    const asReviewer: Project = {
      ...PROJECT,
      membership: { ...PROJECT.membership, role: "reviewer" },
      permissions: ["view", "screen", "export"],
    };
    mockApi({
      ...signedIn,
      ...projectRoutes(asReviewer),
      [`GET ${base}/dedup/summary`]: SUMMARY,
      [`GET ${base}/dedup/clusters`]: [CLUSTER],
    });
    renderApp(`/p/${PROJECT.id}/duplicates`);

    expect(await screen.findByRole("article")).toBeVisible();
    expect(screen.queryByRole("button", { name: /Merge, keeping/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Find duplicates" })).toBeNull();
    expect(screen.getAllByRole("radio")[0]).toBeDisabled();
  });
});
