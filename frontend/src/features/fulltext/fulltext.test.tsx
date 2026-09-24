import { fireEvent, screen, waitFor, within } from "@testing-library/react";
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

describe("a record's PDF, read and worked on", () => {
  function readable(extra: Record<string, unknown> = {}) {
    return routes({
      [`GET ${base}/screening/queue`]: {
        items: [item("r1", "Kidney stones on CT", { fulltext: pdf("r1", "clean") })],
      },
      [`GET ${base}/records/r1/fulltext`]: { fulltext: pdf("r1", "clean"), not_retrievable: false },
      [`GET ${base}/records/r1/fulltext/url`]: (request: Request) => ({
        url: new URL(request.url).searchParams.get("download")
          ? "/api/v1/files/download"
          : "/api/v1/files/tok123",
        expires_in: 300,
      }),
      "GET /api/v1/files/tok123": () => new Response(new Uint8Array([37, 80, 68, 70, 45])),
      [`GET ${base}/fulltext/f-r1/annotations`]: [
        {
          id: "a1",
          page: 2,
          rects: [[0.1, 0.2, 0.5, 0.02]],
          color: "green",
          quote: "sensitivity 0.94",
          comment: null,
          author: USER.name,
          mine: true,
          created_at: "2026-09-24T10:00:00Z",
        },
        {
          id: "a2",
          page: 3,
          rects: [[0.1, 0.2, 0.5, 0.02]],
          color: "pink",
          quote: "specificity",
          comment: "Check the reference standard",
          author: "Grace Hopper",
          mine: false,
          created_at: "2026-09-24T10:00:00Z",
        },
      ],
      [`PATCH ${base}/fulltext/f-r1/annotations/a1`]: async (request: Request) => ({
        id: "a1",
        page: 2,
        rects: [[0.1, 0.2, 0.5, 0.02]],
        color: "green",
        quote: "sensitivity 0.94",
        comment: ((await request.clone().json()) as { comment: string }).comment,
        author: USER.name,
        mine: true,
        created_at: "2026-09-24T10:00:00Z",
      }),
      [`DELETE ${base}/fulltext/f-r1/annotations/a1`]: () => new Response(null, { status: 204 }),
      ...extra,
    });
  }

  test("highlights are listed; my comments can be written and my highlights deleted", async () => {
    const server = mockApi(readable());
    const user = userEvent.setup();
    renderApp(page);

    const viewer = await screen.findByRole("document", { name: /Kidney stones on CT/ });
    await user.click(within(viewer).getByRole("button", { name: /Highlights.*\(2\)/ }));
    const sheet = await screen.findByRole("dialog", { name: "Highlights" });
    expect(within(sheet).getByText("Grace Hopper", { exact: false })).toBeVisible();
    expect(within(sheet).getByText("Check the reference standard")).toBeVisible();

    await user.type(within(sheet).getByLabelText("Comment"), "Primary outcome");
    await user.click(within(sheet).getByRole("button", { name: "Save comment" }));
    await waitFor(() => {
      expect(server.calls(`PATCH ${base}/fulltext/f-r1/annotations/a1`)).toHaveLength(1);
    });
    const [saved] = server.calls(`PATCH ${base}/fulltext/f-r1/annotations/a1`);
    expect(await saved?.json()).toEqual({ comment: "Primary outcome" });

    await user.click(within(sheet).getByRole("button", { name: /page 2/ }));
    await user.click(within(sheet).getByRole("button", { name: "Delete" }));
    await waitFor(() => {
      expect(within(sheet).queryByText("sensitivity 0.94")).not.toBeInTheDocument();
    });
  });

  test("download follows a link that answers as an attachment; replace uploads anew", async () => {
    const clicked: string[] = [];
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clicked.push(this.href);
    });
    const server = mockApi(
      readable({ [`POST ${base}/records/r1/fulltext`]: pdf("r1", "pending") }),
    );
    const user = userEvent.setup();
    renderApp(page);

    const viewer = await screen.findByRole("document", { name: /Kidney stones on CT/ });
    await user.click(within(viewer).getByRole("button", { name: "Download the PDF" }));
    await waitFor(() => {
      expect(clicked).toEqual([`${window.location.origin}/api/v1/files/download`]);
    });
    click.mockRestore();

    const input = viewer.querySelector<HTMLInputElement>('input[type="file"]');
    if (!input) throw new Error("no replace input");
    await user.upload(input, new File(["%PDF-1.4"], "better.pdf", { type: "application/pdf" }));
    await waitFor(() => {
      expect(server.calls(`POST ${base}/records/r1/fulltext`)).toHaveLength(1);
    });
  });

  test("a record marked not retrievable can be put back", async () => {
    let marked = true;
    mockApi(
      routes({
        [`GET ${base}/fulltext/records`]: [{ ...RECORD_ROW, not_retrievable: true }],
        [`GET ${base}/records/r3/fulltext`]: () => ({
          fulltext: null,
          not_retrievable: marked,
          not_retrievable_note: marked ? "Library has no access" : null,
        }),
        [`DELETE ${base}/records/r3/fulltext/not-retrievable`]: () => {
          marked = false;
          return { fulltext: null, not_retrievable: false, not_retrievable_note: null };
        },
      }),
    );
    const user = userEvent.setup();
    renderApp(`${page}?view=pdfs`);

    await user.click(await screen.findByRole("button", { name: /^Ureteric calculi/ }));
    const sheet = await screen.findByRole("dialog", { name: "Ureteric calculi" });
    expect(within(sheet).getByText("Library has no access")).toBeVisible();
    await user.click(within(sheet).getByRole("button", { name: "It was found after all" }));
    expect(await within(sheet).findByText(/Drop the PDF here/)).toBeVisible();
  });

  test("a scan that could not run says so; a viewer sees that no PDF was added", async () => {
    mockApi(
      routes({
        [`GET ${base}/fulltext/records`]: [RECORD_ROW],
        [`GET ${base}/records/r3/fulltext`]: {
          fulltext: pdf("r3", "error"),
          not_retrievable: false,
        },
      }),
    );
    const user = userEvent.setup();
    renderApp(`${page}?view=pdfs`);
    await user.click(await screen.findByRole("button", { name: /^Ureteric calculi/ }));
    expect(await screen.findByText(/could not check Okafor 2020.pdf/)).toBeVisible();
  });

  test("a PDF dropped onto its record in the list is uploaded to that record", async () => {
    const server = mockApi(
      routes({
        [`GET ${base}/fulltext/records`]: [RECORD_ROW],
        [`POST ${base}/records/r3/fulltext`]: pdf("r3", "pending"),
      }),
    );
    const user = userEvent.setup();
    renderApp(`${page}?view=pdfs`);
    const list = await screen.findByRole("region", { name: "List of records at full text" });
    await user.upload(
      within(list).getByLabelText(/Add the PDF for Ureteric calculi/),
      new File(["%PDF-1.4"], "calculi.pdf", { type: "application/pdf" }),
    );
    await waitFor(() => {
      expect(server.calls(`POST ${base}/records/r3/fulltext`)).toHaveLength(1);
    });

    const row = within(list).getByRole("button", { name: /^Ureteric calculi/ }).parentElement;
    if (!row) throw new Error("no row");
    const file = new File(["%PDF-1.4"], "again.pdf", { type: "application/pdf" });
    fireEvent.dragOver(row, { dataTransfer: { files: [file] } });
    fireEvent.drop(row, { dataTransfer: { files: [file] } });
    await waitFor(() => {
      expect(server.calls(`POST ${base}/records/r3/fulltext`)).toHaveLength(2);
    });
  });
});

const RECORD_ROW = {
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
};

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

  test("a ZIP the worker refused says why; a matched one can be discarded", async () => {
    const batch = (id: string, status: string) => ({
      id,
      filename: "papers.zip",
      size_bytes: 100,
      status,
      problem: status === "rejected" ? "paper.pdf unpacks to more than it says it does" : null,
      created_at: "2026-09-24T10:00:00Z",
      entries:
        status === "rejected"
          ? []
          : [{ index: 0, name: "x.pdf", size: 10, skip: null, match: null, candidates: [] }],
    });
    const uploads = ["b2", "b3"];
    const server = mockApi(
      routes({
        [`GET ${base}/fulltext/records`]: RECORDS,
        [`POST ${base}/fulltext/bulk`]: () => batch(uploads.shift() ?? "b9", "checking"),
        [`GET ${base}/fulltext/bulk/b2`]: batch("b2", "rejected"),
        [`GET ${base}/fulltext/bulk/b3`]: batch("b3", "ready"),
        [`DELETE ${base}/fulltext/bulk/b3`]: () => new Response(null, { status: 204 }),
      }),
    );
    const user = userEvent.setup();
    renderApp(`${page}?view=pdfs`);

    const zip = () => new File(["PK"], "papers.zip", { type: "application/zip" });
    await user.upload(await screen.findByLabelText("choose one"), zip());
    expect(await screen.findByText(/unpacks to more than it says/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Upload another" }));

    await user.upload(await screen.findByLabelText("choose one"), zip());
    expect(await screen.findByText("No match from its name")).toBeVisible();
    expect(screen.getByRole("button", { name: "Attach 0 PDFs" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Discard the ZIP" }));
    await waitFor(() => {
      expect(server.calls(`DELETE ${base}/fulltext/bulk/b3`)).toHaveLength(1);
    });
    expect(await screen.findByLabelText("choose one")).toBeInTheDocument();
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
