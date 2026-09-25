import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import type { Project } from "@/api/projects";
import { describe as describeAction } from "@/features/report/audit-words";
import { PROJECT, USER, mockApi, problemResponse, projectRoutes } from "@/test/api";
import { renderApp } from "@/test/render-app";

const base = `/api/v1/projects/${PROJECT.id}`;
const report = `/p/${PROJECT.id}/report`;

const FLOW = {
  database_sources: [{ name: "PubMed", count: 6 }],
  other_sources: [],
  records_identified: 6,
  duplicates_removed: 0,
  records_removed_other_reasons: 0,
  records_screened: 6,
  records_excluded: 2,
  reports_sought: 3,
  reports_not_retrieved: 0,
  reports_assessed: 3,
  reports_excluded: [{ reason: "Wrong population", count: 1 }],
  reports_excluded_total: 1,
  studies_included: 2,
  awaiting_title_abstract: 1,
  awaiting_full_text: 0,
  manual: { other_sources: [], removed_other_reasons: 0, updated_at: null },
};

const VIEWER: Project = {
  ...PROJECT,
  membership: { ...PROJECT.membership, role: "viewer" },
  permissions: ["view", "export"],
};

function routes(extra: Record<string, unknown> = {}, project: Project = PROJECT) {
  return {
    "GET /api/v1/auth/me": USER,
    ...projectRoutes(project),
    [`GET ${base}/prisma`]: FLOW,
    ...extra,
  };
}

describe("PRISMA", () => {
  test("the diagram, its numbers, and a warning while screening is unfinished", async () => {
    mockApi(routes());
    renderApp(report);

    const diagram = await screen.findByRole("img", { name: /PRISMA 2020 flow diagram/ });
    expect(diagram.getAttribute("src")).toMatch(new RegExp(`${base}/prisma\\.svg\\?inline=true`));
    expect(screen.getByText(/1 record waits at title and abstract/)).toBeVisible();
    expect(screen.getByRole("link", { name: "PNG (300 dpi)" })).toHaveAttribute(
      "href",
      `${base}/prisma.png`,
    );
    const numbers = screen.getByRole("table", { name: "PRISMA 2020 counts" });
    expect(within(numbers).getByRole("row", { name: "Records from PubMed 6" })).toBeInTheDocument();
    expect(
      within(numbers).getByRole("row", { name: "Reports excluded: Wrong population 1" }),
    ).toBeInTheDocument();
    // Owners and admins see the audit log among the report's sections.
    expect(screen.getByRole("link", { name: "Audit log" })).toBeVisible();
  });

  test("an admin adds other sources; bad counts are explained before anything is sent", async () => {
    const server = mockApi(
      routes({
        [`PATCH ${base}/prisma/manual`]: {
          other_sources: [{ name: "Citation searching", count: 3 }],
          removed_other_reasons: 2,
          updated_at: "2026-09-25T10:00:00Z",
        },
      }),
    );
    const user = userEvent.setup();
    renderApp(report);

    await user.click(await screen.findByRole("button", { name: "Add a source" }));
    await user.type(screen.getByRole("textbox", { name: "Source 1" }), "Citation searching");
    const count = screen.getByRole("textbox", { name: "Records" });
    await user.clear(count);
    await user.type(count, "three");
    await user.click(screen.getByRole("button", { name: "Save counts" }));
    expect(
      await screen.findByText("Give Citation searching a whole number of records."),
    ).toBeVisible();

    await user.clear(count);
    await user.type(count, "3");
    await user.click(screen.getByRole("button", { name: "Add a source" }));
    await user.type(screen.getByRole("textbox", { name: "Source 2" }), "citation searching");
    await user.click(screen.getByRole("button", { name: "Save counts" }));
    expect(await screen.findByText("Each source needs its own name.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Remove source 2" }));

    const removed = screen.getByLabelText("Records removed before screening, other reasons");
    await user.clear(removed);
    await user.type(removed, "2");
    await user.click(screen.getByRole("button", { name: "Save counts" }));
    expect(await screen.findByText("Saved. The diagram is up to date.")).toBeVisible();
    const [sent] = server.calls(`PATCH ${base}/prisma/manual`);
    expect(await sent?.json()).toEqual({
      other_sources: [{ name: "Citation searching", count: 3 }],
      removed_other_reasons: 2,
    });
  });

  test("a flow that does not add up is explained, and can be corrected", async () => {
    mockApi(
      routes({
        [`GET ${base}/prisma`]: () =>
          problemResponse(422, {
            title: "Unprocessable",
            code: "prisma_inconsistent",
            detail: "More records were removed than identified.",
          }),
      }),
    );
    renderApp(report);
    expect(
      await screen.findByText(/The numbers do not add up, so the diagram is not drawn/),
    ).toBeVisible();
    expect(screen.getByRole("heading", { name: "What Winnow cannot count" })).toBeVisible();
  });

  test("a viewer reads the flow but changes nothing, and has no audit log", async () => {
    mockApi(routes({}, VIEWER));
    renderApp(report);
    expect(await screen.findByRole("img", { name: /PRISMA 2020 flow diagram/ })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "What Winnow cannot count" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Audit log" })).toBeNull();
  });
});

const PAIR = {
  reviewer_a: "Ada Lovelace",
  reviewer_b: "Grace Hopper",
  records: 6,
  percent: 0.8333,
  kappa: 0.67,
  band: "substantial",
};

function stage(name: "title_abstract" | "full_text", extra: Record<string, unknown> = {}) {
  return {
    stage: name,
    records: 6,
    decided: 5,
    conflicts: 1,
    reviewers: [
      {
        user_id: USER.id,
        name: USER.name,
        mine: true,
        decided: 6,
        included: 4,
        excluded: 2,
        maybe: 0,
        median_seconds: 12.5,
      },
    ],
    per_day: [{ day: new Date().toISOString().slice(0, 10), decisions: 12 }],
    agreement: {
      pairs: [PAIR],
      fleiss_kappa: null,
      fleiss_band: null,
      fleiss_records: 0,
      raters: 2,
    },
    ...extra,
  };
}

describe("statistics", () => {
  test("progress per reviewer, decisions per day and agreement", async () => {
    mockApi(
      routes({
        [`GET ${base}/stats`]: {
          blind: false,
          stages: [
            stage("title_abstract", {
              agreement: {
                pairs: [
                  PAIR,
                  { ...PAIR, reviewer_b: "Hedy Lamarr", kappa: null, band: null, percent: null },
                ],
                fleiss_kappa: 0.61,
                fleiss_band: "substantial",
                fleiss_records: 4,
                raters: 3,
              },
            }),
            stage("full_text", {
              reviewers: [],
              per_day: [],
              conflicts: null,
              agreement: {
                pairs: [],
                fleiss_kappa: null,
                fleiss_band: null,
                fleiss_records: 0,
                raters: 2,
              },
            }),
          ],
        },
      }),
    );
    renderApp(`${report}/stats`);

    const agreement = await screen.findByRole("table", {
      name: "Title and abstract: agreement between reviewers",
    });
    expect(
      within(agreement).getByRole("row", { name: /Ada Lovelace and Grace Hopper/ }),
    ).toHaveTextContent("683.3%0.67substantial");
    expect(within(agreement).getByRole("row", { name: /Hedy Lamarr/ })).toHaveTextContent(
      "Not calculable",
    );
    expect(screen.getByText(/Fleiss' κ over the 4 records decided by 3 reviewers/)).toBeVisible();
    const progress = screen.getByRole("table", {
      name: "Title and abstract: progress per reviewer",
    });
    expect(within(progress).getByText("(you)").closest("tr")).toHaveTextContent("12.5 s");
    expect(
      screen.getByRole("progressbar", { name: "Title and abstract: records decided" }),
    ).toHaveAttribute("aria-valuenow", "83");
    expect(
      screen.getByRole("table", { name: "Title and abstract: decisions per day" }),
    ).toHaveTextContent("12");
    expect(screen.getByText("No decisions at this stage yet.")).toBeVisible();
    expect(screen.getByText(/Agreement appears once two reviewers/)).toBeVisible();
  });

  test("a blinded reviewer is told they see their own numbers only", async () => {
    mockApi(
      routes({
        [`GET ${base}/stats`]: {
          blind: true,
          stages: [stage("title_abstract", { agreement: null })],
        },
      }),
    );
    renderApp(`${report}/stats`);
    expect(
      await screen.findByText(/Blind mode is on, so you see your own screening only/),
    ).toBeVisible();
    expect(screen.queryByRole("table", { name: /agreement/ })).toBeNull();
  });
});

function job(extra: Record<string, unknown> = {}) {
  return {
    id: "e1",
    kind: "records",
    format: "csv",
    status: "ready",
    filename: "shift-work-2026-09-25-records.csv",
    size_bytes: 2048,
    rows: 6,
    problem: null,
    created_at: new Date().toISOString(),
    expires_at: null,
    ...extra,
  };
}

describe("exports", () => {
  test("records are asked for with the table's filters, then downloaded when ready", async () => {
    let asked = false;
    let polls = 0;
    const server = mockApi(
      routes({
        [`GET ${base}/records/facets`]: {
          title_abstract: [{ value: "included", label: "Included", count: 4 }],
          full_text: [{ value: "included", label: "Included", count: 2 }],
          years: [],
          imports: [],
          duplicates: 0,
          total: 6,
        },
        [`GET ${base}/exports`]: () => {
          if (!asked)
            return [
              job({
                id: "old",
                status: "failed",
                filename: null,
                rows: null,
                size_bytes: null,
                problem: "The account that asked for this export is gone.",
              }),
            ];
          polls += 1;
          return [job({ status: polls > 1 ? "ready" : "running" })];
        },
        [`POST ${base}/exports`]: () => {
          asked = true;
          return job({ status: "queued" });
        },
      }),
    );
    const user = userEvent.setup();
    renderApp(`${report}/exports`);

    expect(
      await screen.findByText("The account that asked for this export is gone."),
    ).toBeVisible();
    screen.getByLabelText("Format").focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("option", { name: "Excel (XLSX)" }));
    screen.getByLabelText("Title and abstract").focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("option", { name: "Included (4)" }));
    await user.click(screen.getByLabelText(/Include records merged as duplicates/));
    await user.click(screen.getByRole("button", { name: "Make the file" }));

    const [sent] = server.calls(`POST ${base}/exports`);
    expect(await sent?.json()).toEqual({
      kind: "records",
      format: "xlsx",
      filters: { q: "", status: "included", full_text: null, duplicates: true },
    });
    expect(await screen.findByText("Being made")).toBeVisible();
    const download = await screen.findByRole("link", { name: /Download/ }, { timeout: 4000 });
    expect(download).toHaveAttribute("href", `${base}/exports/e1/file`);
    expect(screen.getByText(/6 rows · 2.0 KB/)).toBeVisible();
  });

  test("the owner can make a full backup; others are not offered one", async () => {
    const server = mockApi(
      routes({
        [`GET ${base}/exports`]: [],
        [`POST ${base}/exports`]: job({ kind: "backup", format: "zip", status: "queued" }),
      }),
    );
    const user = userEvent.setup();
    const { unmount } = renderApp(`${report}/exports`);

    expect(await screen.findByText("Nothing yet. Files you make appear here.")).toBeVisible();
    await user.click(screen.getByText("Full backup"));
    expect(screen.getByText(/A ZIP of every record, decision, note/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Make a backup" }));
    const [sent] = server.calls(`POST ${base}/exports`);
    expect(await sent?.json()).toEqual({ kind: "backup", format: "zip" });
    unmount();

    mockApi(routes({ [`GET ${base}/exports`]: [] }, VIEWER));
    renderApp(`${report}/exports`);
    expect(await screen.findByRole("button", { name: "Make the file" })).toBeVisible();
    expect(screen.queryByText("Full backup")).toBeNull();
  });
});

function entry(id: number, extra: Record<string, unknown> = {}) {
  return {
    id,
    at: "2026-09-25T09:00:00Z",
    action: "decision.made",
    actor: "Grace Hopper",
    actor_id: "u2",
    entity_type: "record",
    entity_id: "r1",
    before: null,
    after: { decision: "include" },
    withheld: false,
    ip: "10.0.0.2",
    user_agent: null,
    ...extra,
  };
}

describe("audit log", () => {
  test("entries in words, withheld while blind, filtered, and paged", async () => {
    const server = mockApi(
      routes({
        [`GET ${base}/audit`]: (request: Request) => {
          const query = new URL(request.url).searchParams;
          if (query.get("cursor") === "next") {
            return {
              items: [entry(1, { action: "project.created", actor: null, after: null })],
              next_cursor: null,
            };
          }
          if (query.get("action") === "export") {
            return { items: [entry(5, { action: "export.requested" })], next_cursor: null };
          }
          return {
            items: [entry(3), entry(2, { withheld: true, after: null, action: "rob.saved" })],
            next_cursor: "next",
          };
        },
      }),
    );
    const user = userEvent.setup();
    renderApp(`${report}/audit`);

    expect(await screen.findByText("decided on a record")).toBeVisible();
    expect(screen.getByText(/What was decided is hidden while you are blind/)).toBeVisible();
    await user.click(screen.getByText("Details"));
    expect(screen.getByText(/"decision": "include"/)).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Show older" }));
    const oldest = await screen.findByText("created the review");
    expect(oldest.closest("p")).toHaveTextContent("Winnow created the review");

    screen.getByLabelText("What").focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("option", { name: "Exports" }));
    expect(await screen.findByText("asked for an export")).toBeVisible();
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-09-01" } });
    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Download as CSV" })).toHaveAttribute(
        "href",
        `${base}/audit.csv?action=export&since=2026-09-01`,
      );
    });
    expect(server.calls(`GET ${base}/audit`).some((r) => r.url.includes("since=2026-09-01"))).toBe(
      true,
    );
  });

  test("actions are described in words, and unknown ones by their code", () => {
    expect(describeAction("conflict.resolved")).toBe("resolved a conflict");
    expect(describeAction("worker.queue_drained")).toBe("worker: queue drained");
  });

  test("the audit log is not shown to members below admin", async () => {
    mockApi(routes({}, VIEWER));
    renderApp(`${report}/audit`);
    expect(
      await screen.findByText("The audit log is for the review's owners and admins."),
    ).toBeVisible();
  });
});

describe("restoring a backup", () => {
  test("upload, wait, and open the restored review", async () => {
    let polls = 0;
    const server = mockApi({
      "GET /api/v1/auth/me": USER,
      "POST /api/v1/restores": {
        id: "rs1",
        filename: "backup.zip",
        status: "queued",
        project_id: null,
        problem: null,
        restored: {},
        created_at: "2026-09-25T10:00:00Z",
      },
      "GET /api/v1/restores/rs1": () => {
        polls += 1;
        return {
          id: "rs1",
          filename: "backup.zip",
          status: polls > 1 ? "ready" : "running",
          project_id: polls > 1 ? PROJECT.id : null,
          problem: null,
          restored: polls > 1 ? { records: 6 } : {},
          created_at: "2026-09-25T10:00:00Z",
        };
      },
    });
    const user = userEvent.setup();
    renderApp("/");

    await user.click(await screen.findByRole("link", { name: "Restore a backup" }));
    const restore = await screen.findByRole("button", { name: "Restore" });
    expect(restore).toBeDisabled();
    await user.upload(
      screen.getByLabelText("Backup file (.zip)"),
      new File(["PK"], "backup.zip", { type: "application/zip" }),
    );
    await user.click(restore);
    expect(await screen.findByText(/Checking the backup and rebuilding the review/)).toBeVisible();
    expect(
      await screen.findByText(/Restored 6 records with their decisions/, undefined, {
        timeout: 4000,
      }),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: "Open the restored review" })).toHaveAttribute(
      "href",
      `/p/${PROJECT.id}`,
    );
    const [sent] = server.calls("POST /api/v1/restores");
    expect(sent?.form?.get("file")).toBeInstanceOf(File);
  });

  test("a refused backup says why, and another can be tried", async () => {
    mockApi({
      "GET /api/v1/auth/me": USER,
      "POST /api/v1/restores": {
        id: "rs2",
        filename: "backup.zip",
        status: "queued",
        project_id: null,
        problem: null,
        restored: {},
        created_at: "2026-09-25T10:00:00Z",
      },
      "GET /api/v1/restores/rs2": {
        id: "rs2",
        filename: "backup.zip",
        status: "failed",
        project_id: null,
        problem: "This is not a Winnow project backup.",
        restored: {},
        created_at: "2026-09-25T10:00:00Z",
      },
    });
    const user = userEvent.setup();
    renderApp("/restore");

    await user.upload(
      await screen.findByLabelText("Backup file (.zip)"),
      new File(["PK"], "other.zip", { type: "application/zip" }),
    );
    await user.click(screen.getByRole("button", { name: "Restore" }));
    expect(
      await screen.findByText(/This is not a Winnow project backup. Nothing was kept./),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Try another file" }));
    expect(screen.getByLabelText("Backup file (.zip)")).toBeVisible();
  });

  test("an upload the server refuses is explained", async () => {
    mockApi({
      "GET /api/v1/auth/me": USER,
      "POST /api/v1/restores": () =>
        problemResponse(413, { title: "Too large", detail: "The backup is larger than 2 GB." }),
    });
    const user = userEvent.setup();
    renderApp("/restore");
    await user.upload(
      await screen.findByLabelText("Backup file (.zip)"),
      new File(["PK"], "huge.zip", { type: "application/zip" }),
    );
    await user.click(screen.getByRole("button", { name: "Restore" }));
    expect(await screen.findByText("The backup is larger than 2 GB.")).toBeVisible();
  });
});
