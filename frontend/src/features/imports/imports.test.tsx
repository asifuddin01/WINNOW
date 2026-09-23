import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import type { Project } from "@/api/projects";
import { PROJECT, USER, json, mockApi, problemResponse, projectRoutes } from "@/test/api";
import { renderApp } from "@/test/render-app";

const signedIn = { "GET /api/v1/auth/me": USER };
const base = `/api/v1/projects/${PROJECT.id}`;

const BATCH = {
  id: "b1",
  filename: "pubmed.ris",
  file_format: "ris",
  status: "queued",
  source_name: "PubMed 2026-09-23",
  database_name: "PubMed",
  search_date: null,
  search_string: null,
  size_bytes: 4096,
  total: 0,
  imported: 0,
  problems: [],
  created_at: "2026-09-23T09:00:00Z",
  updated_at: "2026-09-23T09:00:00Z",
};

const PREVIEW = {
  batch: BATCH,
  records: [
    {
      title: "Rotating night shifts and sleep quality",
      authors: ["Smith, Jane A"],
      year: 2019,
      journal: "Journal of Advanced Nursing",
      doi: "10.1111/jan.13894",
      pmid: "31234567",
      abstract: "AIM: to examine whether rotating night shifts affect sleep.",
    },
  ],
  problems: [{ at: 42, unit: "line", reason: "no title, DOI or PubMed id" }],
  columns: [],
  suggested_mapping: {},
  sample_rows: [],
};

function file(name = "pubmed.ris", body = "TY  - JOUR\nTI  - A record\nER  - \n") {
  return new File([body], name, { type: "application/x-research-info-systems" });
}

/** jsdom has no EventSource; this one lets a test send what the server would. */
function fakeEvents() {
  const sources: { url: string; onmessage?: (event: MessageEvent<string>) => void }[] = [];
  class FakeEventSource {
    onmessage?: (event: MessageEvent<string>) => void;
    readonly url: string;
    constructor(url: string) {
      this.url = url;
      sources.push(this);
    }
    readonly close = () => undefined;
  }
  vi.stubGlobal("EventSource", FakeEventSource);
  return {
    sources,
    send: (data: Record<string, unknown>) =>
      act(async () => {
        for (const source of sources) {
          source.onmessage?.(new MessageEvent("message", { data: JSON.stringify(data) }));
        }
        // Let the refetch the event asks for start before the test looks for its result.
        await Promise.resolve();
      }),
  };
}

/** The preview and confirm routes for a whole drop of files. */
function previewRoutes(batches: { id: string }[]): Record<string, unknown> {
  const routes: Record<string, unknown> = {};
  for (const batch of batches) {
    routes[`GET ${base}/imports/${batch.id}/preview`] = { ...PREVIEW, batch, problems: [] };
    routes[`POST ${base}/imports/${batch.id}/confirm`] = { batch, job_id: `j${batch.id}` };
  }
  return routes;
}

describe("the import page", () => {
  test("uploading a file shows what Winnow read before anything is imported", async () => {
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`POST ${base}/imports`]: { batches: [BATCH], rejected: [] },
      [`GET ${base}/imports/b1/preview`]: PREVIEW,
      [`POST ${base}/imports/b1/confirm`]: { batch: { ...BATCH, status: "parsing" }, job_id: "j1" },
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/import`);

    await user.upload(await screen.findByLabelText("Search export files"), file());
    await user.click(screen.getByRole("button", { name: "Upload and preview" }));

    expect(await screen.findByText("Rotating night shifts and sleep quality")).toBeVisible();
    expect(screen.getByText(/1 entry near the start could not be read/)).toBeVisible();
    const upload = server.calls(`POST ${base}/imports`)[0];
    expect(upload).toBeDefined();

    await user.click(screen.getByRole("button", { name: "Import these records" }));
    expect(server.calls(`POST ${base}/imports/b1/confirm`)).toHaveLength(1);
  });

  test("a CSV asks which column holds what", async () => {
    const csvBatch = { ...BATCH, id: "b2", filename: "scopus.csv", file_format: "csv" };
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`POST ${base}/imports`]: { batches: [csvBatch], rejected: [] },
      [`GET ${base}/imports/b2/preview`]: {
        ...PREVIEW,
        batch: csvBatch,
        problems: [],
        columns: ["Title", "Source title", "Nickname"],
        suggested_mapping: { Title: "title", "Source title": "journal" },
        sample_rows: [{ Title: "A record", "Source title": "BMJ", Nickname: "x" }],
      },
      [`POST ${base}/imports/b2/confirm`]: { batch: csvBatch, job_id: "j2" },
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/import`);

    await user.upload(
      await screen.findByLabelText("Search export files"),
      file("scopus.csv", "Title,Source title\nA record,BMJ\n"),
    );
    await user.click(screen.getByRole("button", { name: "Upload and preview" }));

    expect(await screen.findByText("Which column holds what?")).toBeVisible();
    // The guess is shown, and can be changed before confirming.
    expect(screen.getByLabelText("Source title")).toHaveTextContent("Journal");
    screen.getByLabelText("Nickname").focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("option", { name: "Keywords" }));
    await user.click(screen.getByRole("button", { name: "Import these records" }));

    expect(await server.calls(`POST ${base}/imports/b2/confirm`)[0]?.json()).toEqual({
      column_mapping: { Title: "title", "Source title": "journal", Nickname: "keywords" },
    });
  });

  test("a whole search goes up at once, one import per file", async () => {
    const batches = ["pubmed.ris", "scopus.ris", "ieee_xplore.ris"].map((filename, index) => ({
      ...BATCH,
      id: `b${index + 10}`,
      filename,
      database_name: filename.split(/[._]/)[0],
    }));
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`POST ${base}/imports`]: {
        batches,
        rejected: [{ filename: "notes.txt", reason: "Winnow could not read that file." }],
      },
      ...previewRoutes(batches),
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/import`);

    const picker = await screen.findByLabelText("Search export files");
    await user.upload(picker, [file("pubmed.ris"), file("scopus.ris"), file("ieee_xplore.ris")]);

    // Winnow names the database from each file, and they can be corrected before upload.
    expect(await screen.findByText("3 files ready")).toBeVisible();
    expect(screen.getByLabelText("Database for pubmed.ris")).toHaveTextContent("PubMed");
    expect(screen.getByLabelText("Database for scopus.ris")).toHaveTextContent("Scopus");
    expect(screen.getByLabelText("Database for ieee_xplore.ris")).toHaveTextContent("IEEE Xplore");

    await user.click(screen.getByRole("button", { name: /Upload and preview 3 files/ }));

    expect(await screen.findByText(/1 file could not be read/)).toBeVisible();
    expect(screen.getByText("notes.txt")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Import all 3 files" }));

    for (const batch of batches) {
      expect(server.calls(`POST ${base}/imports/${batch.id}/confirm`)).toHaveLength(1);
    }
    const upload = server.calls(`POST ${base}/imports`)[0];
    expect(upload?.form?.getAll("files")).toHaveLength(3);
    expect(upload?.form?.getAll("databases")).toEqual(["PubMed", "Scopus", "IEEE Xplore"]);
  });

  test("a file can be taken back out of the drop before it is uploaded", async () => {
    mockApi({ ...signedIn, ...projectRoutes() });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/import`);

    await user.upload(await screen.findByLabelText("Search export files"), [
      file("pubmed.ris"),
      file("scopus.ris"),
    ]);
    expect(await screen.findByText("2 files ready")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Remove scopus.ris" }));
    expect(await screen.findByText("1 file ready")).toBeVisible();
    expect(screen.queryByText("scopus.ris")).toBeNull();
  });

  test("the history shows what came in and what could not be read", async () => {
    const done = {
      ...BATCH,
      status: "done",
      total: 12,
      imported: 10,
      problems: [
        { at: 42, unit: "line", reason: "no title, DOI or PubMed id" },
        { at: 88, unit: "line", reason: "no title, DOI or PubMed id" },
      ],
      search_string: "nurses AND shift work",
    };
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`GET ${base}/imports`]: [done],
      [`DELETE ${base}/imports/b1`]: () => json(null, 204),
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/import`);

    expect(await screen.findByText("pubmed.ris")).toBeVisible();
    expect(screen.getByText(/10 records/)).toBeVisible();
    expect(screen.getByText(/2 could not be read/)).toBeVisible();
    expect(screen.getByText(/nurses AND shift work/)).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Undo the import of pubmed.ris" }));
    const dialog = within(await screen.findByRole("alertdialog"));
    expect(dialog.getByText(/10 records this file brought in/)).toBeVisible();
    await user.click(dialog.getByRole("button", { name: "Undo import" }));
    expect(server.calls(`DELETE ${base}/imports/b1`)).toHaveLength(1);
  });

  test("a file Winnow cannot read says so", async () => {
    mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`POST ${base}/imports`]: () =>
        problemResponse(415, {
          title: "Unsupported Media Type",
          code: "unknown_format",
          detail: "Winnow could not read that file.",
        }),
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/import`);

    // The file picker only offers export extensions, so the refusal comes from the
    // server reading the content, which is where it belongs.
    await user.upload(
      await screen.findByLabelText("Search export files"),
      file("holiday.txt", "just some prose"),
    );
    await user.click(screen.getByRole("button", { name: "Upload and preview" }));
    expect(await screen.findByText("Winnow could not read that file.")).toBeVisible();
  });

  test("progress from the server is shown while the import runs", async () => {
    let batch = { ...BATCH, status: "parsing", total: 10_000, imported: 0 };
    mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`GET ${base}/imports`]: () => [batch],
    });
    const events = fakeEvents();
    renderApp(`/p/${PROJECT.id}/import`);

    expect(await screen.findByText("Importing…")).toBeVisible();
    expect(events.sources[0]?.url).toBe(`/api/v1/projects/${PROJECT.id}/events`);

    batch = { ...batch, imported: 5000 };
    await events.send({ event: "import.progress", batch_id: "b1", imported: 5000 });
    expect(await screen.findByText("5,000 records so far…")).toBeVisible();

    batch = { ...batch, status: "done", imported: 10_000 };
    await events.send({ event: "import.finished", batch_id: "b1", imported: 10_000 });
    expect(await screen.findByText(/10,000 records/)).toBeVisible();
  });

  test("a reviewer sees the history but cannot import", async () => {
    const asReviewer: Project = {
      ...PROJECT,
      membership: { ...PROJECT.membership, role: "reviewer" },
      permissions: ["view", "screen", "export"],
    };
    mockApi({ ...signedIn, ...projectRoutes(asReviewer), [`GET ${base}/imports`]: [BATCH] });
    renderApp(`/p/${PROJECT.id}/import`);

    expect(await screen.findByText("pubmed.ris")).toBeVisible();
    expect(screen.queryByLabelText("Search export files")).toBeNull();
    expect(screen.queryByRole("button", { name: /Undo the import/ })).toBeNull();
  });
});
