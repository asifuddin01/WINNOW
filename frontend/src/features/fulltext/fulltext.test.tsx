import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import type { Project } from "@/api/projects";
import { toBoxes } from "@/features/fulltext/geometry";
import type { PdfViewerProps } from "@/features/fulltext/PdfViewer";
import { PROJECT, USER, mockApi, problemResponse, projectRoutes } from "@/test/api";
import { renderApp } from "@/test/render-app";

// jsdom has no canvas: the real viewer is exercised by the Playwright phone test. This
// stand-in shows what it was given and can report a highlight.
vi.mock("@/features/fulltext/PdfViewer", () => ({
  default: (props: PdfViewerProps) => (
    <div role="document" aria-label={`${props.label} (${props.data.length} bytes)`}>
      <button
        type="button"
        onClick={() => {
          props.onHighlight({
            page: 2,
            rects: [[0.1, 0.2, 0.5, 0.02]],
            quote: "0.94",
            color: "green",
          });
        }}
      >
        Pretend to highlight
      </button>
      {props.actions}
    </div>
  ),
}));

const base = `/api/v1/projects/${PROJECT.id}`;
const page = `/p/${PROJECT.id}/screen/ft`;

function item(id: string, title: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    title,
    authors: ["Okafor, Ngozi"],
    year: 2020,
    journal: "Radiology",
    volume: null,
    issue: null,
    pages: null,
    doi: `10.1000/${id}`,
    pmid: null,
    pmcid: null,
    url: null,
    abstract: "About kidney stones.",
    keywords: [],
    publication_type: [],
    relevance_score: null,
    fulltext: null,
    not_retrievable: false,
    my_decision: null,
    labels: [],
    notes: [],
    others: null,
    ...extra,
  };
}

function pdf(rid: string, status: string, extra: Record<string, unknown> = {}) {
  return {
    id: `f-${rid}`,
    record_id: rid,
    filename: "Okafor 2020.pdf",
    size_bytes: 1234,
    scan_status: status,
    page_count: 2,
    source: "upload",
    source_url: null,
    created_at: "2026-09-24T10:00:00Z",
    ...extra,
  };
}

const SUMMARY = {
  records: 3,
  with_pdf: 1,
  scanning: 0,
  quarantined: 1,
  missing: 1,
  not_retrievable: 0,
  scanner: true,
  open_access: true,
};

function routes(extra: Record<string, unknown> = {}, project: Project = PROJECT) {
  return {
    "GET /api/v1/auth/me": USER,
    ...projectRoutes(project),
    [`GET ${base}/fulltext/summary`]: SUMMARY,
    ...extra,
  };
}

describe("full-text screening", () => {
  test("a record without a PDF offers upload; the upload waits for the scanner", async () => {
    let uploaded = false;
    const server = mockApi(
      routes({
        [`GET ${base}/screening/queue`]: { items: [item("r1", "Kidney stones on CT")] },
        [`GET ${base}/records/r1/fulltext`]: () => ({
          fulltext: uploaded ? pdf("r1", "pending") : null,
          not_retrievable: false,
        }),
        [`POST ${base}/records/r1/fulltext`]: () => {
          uploaded = true;
          return pdf("r1", "pending");
        },
      }),
    );
    const user = userEvent.setup();
    renderApp(page);

    expect(await screen.findByRole("heading", { name: "Full-text screening" })).toBeVisible();
    await user.upload(
      await screen.findByLabelText("choose a file"),
      new File(["%PDF-1.4"], "Okafor 2020.pdf", { type: "application/pdf" }),
    );
    expect(await screen.findByText(/Checking Okafor 2020.pdf for viruses/)).toBeVisible();
    const [sent] = server.calls(`POST ${base}/records/r1/fulltext`);
    expect(sent?.form?.get("file")).toBeInstanceOf(File);
    expect(sent?.headers.get("X-CSRF-Token")).toBe("test-csrf-token");
  });

  test("a cleared PDF opens in the viewer, and a selection becomes a highlight", async () => {
    const server = mockApi(
      routes({
        [`GET ${base}/screening/queue`]: {
          items: [item("r1", "Kidney stones on CT", { fulltext: pdf("r1", "clean") })],
        },
        [`GET ${base}/records/r1/fulltext`]: {
          fulltext: pdf("r1", "clean"),
          not_retrievable: false,
        },
        [`GET ${base}/records/r1/fulltext/url`]: { url: "/api/v1/files/tok123", expires_in: 300 },
        "GET /api/v1/files/tok123": () => new Response(new Uint8Array([37, 80, 68, 70, 45])),
        [`GET ${base}/fulltext/f-r1/annotations`]: [],
        [`POST ${base}/fulltext/f-r1/annotations`]: {
          id: "a1",
          page: 2,
          rects: [[0.1, 0.2, 0.5, 0.02]],
          color: "green",
          quote: "0.94",
          comment: null,
          author: USER.name,
          mine: true,
          created_at: "2026-09-24T10:00:00Z",
        },
      }),
    );
    const user = userEvent.setup();
    renderApp(page);

    const viewer = await screen.findByRole("document", { name: "Kidney stones on CT (5 bytes)" });
    await user.click(within(viewer).getByRole("button", { name: "Pretend to highlight" }));
    expect(await within(viewer).findByRole("button", { name: /Highlights.*\(1\)/ })).toBeVisible();
    const [sent] = server.calls(`POST ${base}/fulltext/f-r1/annotations`);
    expect(await sent?.json()).toEqual({
      page: 2,
      rects: [[0.1, 0.2, 0.5, 0.02]],
      quote: "0.94",
      color: "green",
    });
  });

  test("not retrievable takes the record out of the queue without a decision", async () => {
    const server = mockApi(
      routes({
        [`GET ${base}/screening/queue`]: {
          items: [item("r1", "Kidney stones on CT"), item("r2", "Renal cysts")],
        },
        [`GET ${base}/records/r1/fulltext`]: { fulltext: null, not_retrievable: false },
        [`GET ${base}/records/r2/fulltext`]: { fulltext: null, not_retrievable: false },
        [`POST ${base}/records/r1/fulltext/not-retrievable`]: {
          fulltext: null,
          not_retrievable: true,
          not_retrievable_note: "Library has no access",
        },
      }),
    );
    const user = userEvent.setup();
    renderApp(page);

    expect(await screen.findByRole("heading", { name: "Kidney stones on CT" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Not retrievable" }));
    await user.type(
      screen.getByLabelText(/Why could the full text not be found/),
      "Library has no access",
    );
    await user.click(screen.getByRole("button", { name: "Mark not retrievable" }));

    expect(await screen.findByRole("heading", { name: "Renal cysts" })).toBeVisible();
    const [sent] = server.calls(`POST ${base}/records/r1/fulltext/not-retrievable`);
    expect(await sent?.json()).toEqual({ note: "Library has no access" });
    expect(server.calls(`PUT ${base}/records/r1/decision`)).toHaveLength(0);
  });

  test("a quarantined PDF is explained, and cannot be opened", async () => {
    const server = mockApi(
      routes({
        [`GET ${base}/screening/queue`]: {
          items: [item("r1", "Kidney stones on CT", { fulltext: pdf("r1", "infected") })],
        },
        [`GET ${base}/records/r1/fulltext`]: {
          fulltext: pdf("r1", "infected"),
          not_retrievable: false,
        },
      }),
    );
    renderApp(page);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This PDF was quarantined.");
    expect(alert).toHaveTextContent("owners and admins have been told");
    expect(screen.queryByRole("document")).not.toBeInTheDocument();
    expect(server.calls(`GET ${base}/records/r1/fulltext/url`)).toHaveLength(0);
  });

  test("a free copy is found and fetched by the server, chosen by its id", async () => {
    const server = mockApi(
      routes({
        [`GET ${base}/screening/queue`]: { items: [item("r1", "Kidney stones on CT")] },
        [`GET ${base}/records/r1/fulltext`]: { fulltext: null, not_retrievable: false },
        [`POST ${base}/records/r1/fulltext/find-oa`]: {
          candidates: [
            {
              id: "abc123abc123",
              source: "pmc",
              host: "pmc-oa-opendata.s3.amazonaws.com",
              version: "publishedVersion",
              license: "cc-by",
            },
          ],
          note: null,
        },
        [`POST ${base}/records/r1/fulltext/fetch-oa`]: pdf("r1", "pending", {
          source: "open_access",
        }),
      }),
    );
    const user = userEvent.setup();
    renderApp(page);

    await user.click(await screen.findByRole("button", { name: "Find free full text" }));
    expect(await screen.findByText("pmc-oa-opendata.s3.amazonaws.com")).toBeVisible();
    expect(screen.getByText(/PubMed Central · published version · cc-by/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Get this copy" }));
    await waitFor(() => {
      expect(server.calls(`POST ${base}/records/r1/fulltext/fetch-oa`)).toHaveLength(1);
    });
    const [sent] = server.calls(`POST ${base}/records/r1/fulltext/fetch-oa`);
    expect(await sent?.json()).toEqual({ candidate: "abc123abc123" });
  });
});

const RECORDS = [
  {
    id: "r1",
    title: "Kidney stones on CT",
    first_author: "Okafor, Ngozi",
    year: 2020,
    journal: "Radiology",
    doi: "10.1000/r1",
    pmid: null,
    pmcid: null,
    fulltext: pdf("r1", "clean"),
    not_retrievable: false,
  },
  {
    id: "r2",
    title: "Renal cysts",
    first_author: "Chen, Wei",
    year: 2021,
    journal: "Radiology",
    doi: null,
    pmid: null,
    pmcid: null,
    fulltext: pdf("r2", "infected"),
    not_retrievable: false,
  },
  {
    id: "r3",
    title: "Ureteric calculi",
    first_author: "Kowalski, Jan",
    year: 2022,
    journal: null,
    doi: null,
    pmid: null,
    pmcid: null,
    fulltext: null,
    not_retrievable: false,
  },
];

describe("the PDFs view", () => {
  test("counts, filters, and a ZIP bomb refused with the server's reason", async () => {
    mockApi(
      routes({
        [`GET ${base}/fulltext/records`]: RECORDS,
        [`POST ${base}/fulltext/bulk`]: problemResponse(422, {
          title: "Unprocessable Content",
          code: "zip_rejected",
          detail:
            "paper.pdf would unpack to 1,028 times its packed size: this looks like a ZIP bomb, and the ZIP was not opened.",
        }),
      }),
    );
    const user = userEvent.setup();
    renderApp(`${page}?view=pdfs`);

    expect(await screen.findByRole("heading", { name: "Full-text PDFs" })).toBeVisible();
    expect(await screen.findByRole("link", { name: /PDFs \(1 missing\)/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
    const list = await screen.findByRole("region", { name: "List of records at full text" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    await user.click(screen.getByRole("button", { name: "Quarantined" }));
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(within(list).getByText("Renal cysts")).toBeVisible();

    await user.upload(
      screen.getByLabelText("choose one"),
      new File(["PK"], "papers.zip", { type: "application/zip" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("looks like a ZIP bomb");
  });

  test("a ZIP's matches are checked, changed, and confirmed", async () => {
    const server = mockApi(
      routes({
        [`GET ${base}/fulltext/records`]: RECORDS,
        [`POST ${base}/fulltext/bulk`]: {
          id: "b1",
          filename: "papers.zip",
          size_bytes: 100,
          status: "checking",
          problem: null,
          entries: [],
          created_at: "2026-09-24T10:00:00Z",
        },
        [`GET ${base}/fulltext/bulk/b1`]: {
          id: "b1",
          filename: "papers.zip",
          size_bytes: 100,
          status: "ready",
          problem: null,
          created_at: "2026-09-24T10:00:00Z",
          entries: [
            {
              index: 0,
              name: "10.1000_r3.pdf",
              size: 10,
              skip: null,
              match: {
                record_id: "r3",
                title: "Ureteric calculi",
                year: 2022,
                by: "doi",
                confidence: "sure",
                has_fulltext: false,
              },
              candidates: [],
            },
            {
              index: 1,
              name: "Chen 2021.pdf",
              size: 10,
              skip: null,
              match: {
                record_id: "r2",
                title: "Renal cysts",
                year: 2021,
                by: "author_year",
                confidence: "likely",
                has_fulltext: true,
              },
              candidates: [],
            },
            { index: 2, name: "._x.pdf", size: 1, skip: "system", match: null, candidates: [] },
          ],
        },
        [`POST ${base}/fulltext/bulk/b1/confirm`]: { attached: 1, skipped: 1 },
      }),
    );
    const user = userEvent.setup();
    renderApp(`${page}?view=pdfs`);

    await user.upload(
      await screen.findByLabelText("choose one"),
      new File(["PK"], "papers.zip", { type: "application/zip" }),
    );
    expect(await screen.findByText("Sure match by DOI")).toBeVisible();
    expect(screen.getByText("Likely match by author and year")).toBeVisible();
    expect(screen.getByText("1 file left out")).toBeVisible();
    await user.selectOptions(screen.getByLabelText("Record for Chen 2021.pdf"), "Leave out");
    await user.click(screen.getByRole("button", { name: "Attach 1 PDF" }));

    await waitFor(() => {
      expect(server.calls(`POST ${base}/fulltext/bulk/b1/confirm`)).toHaveLength(1);
    });
    const [sent] = server.calls(`POST ${base}/fulltext/bulk/b1/confirm`);
    expect(await sent?.json()).toEqual({ choices: { "0": "r3" }, replace: false });
  });

  test("a viewer sees the PDFs, not the screen, and cannot add any", async () => {
    const viewer: Project = {
      ...PROJECT,
      membership: { ...PROJECT.membership, role: "viewer" },
      permissions: ["view", "export"],
    };
    mockApi(routes({ [`GET ${base}/fulltext/records`]: RECORDS }, viewer));
    renderApp(page);

    expect(await screen.findByRole("heading", { name: "Full-text PDFs" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Screen" })).not.toBeInTheDocument();
    expect(screen.queryByText("Add many PDFs from a ZIP")).not.toBeInTheDocument();
    expect(screen.queryByText(/Add the PDF for/)).not.toBeInTheDocument();
  });
});

describe("selection geometry", () => {
  const pageBox = { left: 100, top: 50, width: 400, height: 800 };

  test("rectangles become fractions of the page, and touching ones on a line join", () => {
    const boxes = toBoxes(
      [
        { left: 140, top: 130, width: 100, height: 16 },
        { left: 240, top: 131, width: 60, height: 15 },
        { left: 140, top: 150, width: 80, height: 16 },
      ],
      pageBox,
    );
    expect(boxes).toHaveLength(2);
    expect(boxes[0]?.map((value) => Number(value.toFixed(4)))).toEqual([0.1, 0.1, 0.4, 0.02]);
    expect(boxes[1]?.[1]).toBeCloseTo(0.125);
  });

  test("empty and off-page rectangles are dropped; the rest are kept on the page", () => {
    expect(toBoxes([{ left: 0, top: 0, width: 0, height: 10 }], pageBox)).toEqual([]);
    expect(
      toBoxes([{ left: 150, top: 60, width: 10, height: 10 }], { ...pageBox, width: 0 }),
    ).toEqual([]);
    const [edge = [0, 0, 0, 0]] = toBoxes(
      [{ left: 450, top: 820, width: 200, height: 100 }],
      pageBox,
    );
    expect(edge[0] + edge[2]).toBeCloseTo(1);
    expect(edge[1] + edge[3]).toBeCloseTo(1);
  });
});
