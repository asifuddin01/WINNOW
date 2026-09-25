import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import type { Project } from "@/api/projects";
import { keyFrom, withValue } from "@/features/extraction/fields";
import { PROJECT, USER, mockApi, problemResponse, projectRoutes } from "@/test/api";
import { renderApp } from "@/test/render-app";

const base = `/api/v1/projects/${PROJECT.id}`;
const page = `/p/${PROJECT.id}/extraction`;
const F1 = "00000000-0000-4000-8000-00000000f001";
const R1 = "00000000-0000-4000-8000-000000000001";

const SCHEMA = {
  fields: [
    { key: "about", label: "About the study", type: "section", help: "From the methods." },
    {
      key: "design",
      label: "Study design",
      type: "select",
      required: true,
      options: ["RCT", "Cohort"],
    },
    { key: "n", label: "Participants", type: "number", unit: "people", integer: true },
    { key: "country", label: "Country", type: "short_text", help: "Where it ran." },
    { key: "notes", label: "Notes", type: "long_text" },
    { key: "outcomes", label: "Outcomes", type: "multi_select", options: ["Sleep", "Fatigue"] },
    { key: "blinded", label: "Assessors blinded", type: "yes_no_unclear" },
    { key: "published", label: "Published on", type: "date" },
    {
      key: "arms",
      label: "Arms",
      type: "table",
      max_rows: 2,
      columns: [
        { key: "arm", label: "Arm", type: "short_text", required: true },
        { key: "mean", label: "Mean", type: "number", unit: "hours" },
      ],
    },
  ],
};

function form(extra: Record<string, unknown> = {}) {
  return {
    id: F1,
    family_id: F1,
    name: "Trial data",
    version: 1,
    schema: SCHEMA,
    dual: true,
    published: true,
    published_at: "2026-09-25T10:00:00Z",
    created_at: "2026-09-25T09:00:00Z",
    updated_at: "2026-09-25T10:00:00Z",
    entries: 3,
    latest: true,
    ...extra,
  };
}

function nth(items: HTMLElement[], index: number): HTMLElement {
  const item = items[index];
  if (!item) throw new Error(`no element ${index}`);
  return item;
}

/** Set a text field at once: typing it key by key is slow under coverage. */
function fill(element: HTMLElement, value: string) {
  fireEvent.change(element, { target: { value } });
}

const STUDY = {
  record_id: R1,
  label: "Okafor 2016",
  title: "Night shifts and sleep",
  mine: "none",
  submitted: 2,
  consensus: false,
};

function routes(extra: Record<string, unknown> = {}, project: Project = PROJECT) {
  return {
    "GET /api/v1/auth/me": USER,
    ...projectRoutes(project),
    [`GET ${base}/extraction-forms`]: [form()],
    [`GET ${base}/extraction-forms/${F1}/studies`]: [STUDY],
    ...extra,
  };
}

describe("helpers", () => {
  test("keys come from labels, as the server accepts them", () => {
    expect(keyFrom("Participants (n)", [])).toBe("participants_n");
    expect(keyFrom("Participants", ["participants"])).toBe("participants_2");
    expect(keyFrom("2nd outcome", [])).toBe("field_2nd_outcome");
    expect(keyFrom("Ödegård", [])).toBe("odegard");
    expect(keyFrom("!!!", [])).toBe("field");
  });

  test("a value is set at a path, table cells included", () => {
    expect(withValue({ n: 1 }, "n", 2)).toEqual({ n: 2 });
    expect(withValue({}, "arms[2].mean", 6)).toEqual({ arms: [{}, { mean: 6 }] });
    expect(withValue({ arms: [{ arm: "A" }] }, "arms[1].mean", 6)).toEqual({
      arms: [{ arm: "A", mean: 6 }],
    });
  });
});

describe("extracting a study", () => {
  test("every kind of field, saved as a draft", async () => {
    const server = mockApi(
      routes({
        [`GET ${base}/extraction-forms/${F1}/entries/${R1}`]: {
          record_id: R1,
          title: "Night shifts and sleep",
          label: "Okafor 2016",
          entries: [],
          consensus: null,
        },
        [`PUT ${base}/extraction-forms/${F1}/entries/${R1}`]: {
          id: "e1",
          record_id: R1,
          form_id: F1,
          data: {},
          status: "draft",
          extractor: USER.name,
          mine: true,
          updated_at: "2026-09-25T10:00:00Z",
        },
      }),
    );
    const user = userEvent.setup();
    renderApp(page);

    await user.click(await screen.findByRole("link", { name: /Okafor 2016/ }));
    expect(await screen.findByRole("heading", { name: "About the study" })).toBeVisible();
    await user.selectOptions(screen.getByLabelText(/Study design/), "RCT");
    fill(screen.getByLabelText(/Participants/), "120");
    fill(screen.getByLabelText("Country"), "Norway");
    fill(screen.getByLabelText("Notes"), "Pilot.");
    const outcomes = screen.getByRole("group", { name: "Outcomes" });
    await user.click(within(outcomes).getByLabelText("Fatigue"));
    await user.click(within(outcomes).getByLabelText("Sleep"));
    await user.click(within(outcomes).getByLabelText("Fatigue"));
    const blinded = screen.getByRole("group", { name: "Assessors blinded" });
    await user.click(within(blinded).getByLabelText("No"));
    await user.click(within(blinded).getByRole("button", { name: "Clear" }));
    await user.click(within(blinded).getByLabelText("Unclear"));
    fireEvent.change(screen.getByLabelText("Published on"), { target: { value: "2016-03-01" } });
    const add = screen.getByRole("button", { name: "Add a row to Arms" });
    await user.click(add);
    await user.click(add);
    expect(add).toBeDisabled(); // two rows at most
    fill(screen.getByLabelText(/Arm, row 1/), "Melatonin");
    fill(screen.getByLabelText(/Mean, row 1/), "6.5");
    await user.click(screen.getByRole("button", { name: "Remove row 2 of Arms" }));
    await user.click(screen.getByRole("button", { name: "Save as draft" }));

    const [sent] = server.calls(`PUT ${base}/extraction-forms/${F1}/entries/${R1}`);
    expect(await sent?.json()).toEqual({
      status: "draft",
      data: {
        design: "RCT",
        n: "120",
        country: "Norway",
        notes: "Pilot.",
        outcomes: ["Sleep"],
        blinded: "unclear",
        published: "2016-03-01",
        arms: [{ arm: "Melatonin", mean: "6.5" }],
      },
    });
  });

  test("the server's problems appear beside their fields", async () => {
    mockApi(
      routes({
        [`GET ${base}/extraction-forms/${F1}/entries/${R1}`]: {
          record_id: R1,
          title: "Night shifts and sleep",
          label: "Okafor 2016",
          entries: [
            {
              id: "e1",
              record_id: R1,
              form_id: F1,
              data: { n: 120, arms: [{ mean: 2 }] },
              status: "draft",
              extractor: USER.name,
              mine: true,
              updated_at: "2026-09-25T10:00:00Z",
            },
          ],
          consensus: { data: {}, resolved_by: "Grace Hopper", updated_at: "2026-09-25T11:00:00Z" },
        },
        [`PUT ${base}/extraction-forms/${F1}/entries/${R1}`]: () =>
          problemResponse(422, {
            title: "Unprocessable",
            code: "invalid_entry",
            detail: "Some values need attention.",
            problems: { design: "Required.", "arms[1].arm": "Required." },
          }),
      }),
    );
    const user = userEvent.setup();
    renderApp(`${page}?form=${F1}&study=${R1}`);

    const participants = await screen.findByLabelText(/Participants/);
    expect(participants).toHaveValue("120");
    expect(screen.getByText(/Reconciled by Grace Hopper/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Submit" }));
    const design = screen.getByLabelText(/Study design/);
    expect(
      await within(design.closest("div") as HTMLElement).findByText("Required."),
    ).toBeVisible();
    expect(design).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText(/Arm, row 1/)).toHaveAttribute("aria-invalid", "true");
  });

  test("no published form: builders are sent to Forms, others told who builds", async () => {
    mockApi(routes({ [`GET ${base}/extraction-forms`]: [form({ published: false })] }));
    const { unmount } = renderApp(page);
    expect(await screen.findByRole("link", { name: "Build one under Forms" })).toBeVisible();
    unmount();

    const viewer: Project = {
      ...PROJECT,
      membership: { ...PROJECT.membership, role: "viewer" },
      permissions: ["view", "export"],
    };
    mockApi(routes({ [`GET ${base}/extraction-forms`]: [] }, viewer));
    renderApp(page);
    expect(await screen.findByText(/An owner or admin builds and publishes one/)).toBeVisible();
    expect(screen.queryByRole("link", { name: "Consensus" })).toBeNull();
  });
});

describe("building forms", () => {
  test("a new form, fields added, reordered and saved, then published", async () => {
    const draft = form({
      id: "00000000-0000-4000-8000-00000000f002",
      dual: false,
      published: false,
      schema: { fields: [] },
      entries: 0,
    });
    const server = mockApi(
      routes({
        [`GET ${base}/extraction-forms`]: [draft],
        [`POST ${base}/extraction-forms`]: draft,
        [`PATCH ${base}/extraction-forms/${draft.id}`]: draft,
        [`POST ${base}/extraction-forms/${draft.id}/publish`]: () =>
          problemResponse(422, {
            title: "Unprocessable",
            code: "invalid_form",
            detail: "The form has problems.",
            problems: ["'Arms': a table needs at least one column."],
          }),
      }),
    );
    const user = userEvent.setup();
    renderApp(`${page}/forms`);

    await user.type(await screen.findByLabelText("New form"), "Trial data");
    await user.click(screen.getByRole("button", { name: "Create" }));
    const [created] = server.calls(`POST ${base}/extraction-forms`);
    expect(await created?.json()).toEqual({
      name: "Trial data",
      dual: false,
      schema: { fields: [] },
    });

    expect(await screen.findByText("No fields yet. Add the first one below.")).toBeVisible();
    const adding = screen.getByRole("group", { name: "Add a field" });
    await user.click(within(adding).getByRole("button", { name: "Number" }));
    await user.click(within(adding).getByRole("button", { name: "Choice" }));
    await user.click(within(adding).getByRole("button", { name: "Table" }));
    const fields = screen.getByRole("list", { name: "Fields" });
    const number = nth(within(fields).getAllByRole("listitem"), 0);
    const label = within(number).getByLabelText("Label");
    await user.clear(label);
    await user.type(label, "Participants (n)");
    expect(within(number).getByLabelText("Column name in exports")).toHaveValue("participants_n");
    await user.type(within(number).getByLabelText("Unit"), "people");
    await user.type(within(number).getByLabelText("Minimum"), "1");
    await user.click(within(number).getByLabelText("Whole numbers only"));
    await user.click(within(number).getByLabelText("Required"));
    await user.click(screen.getByRole("button", { name: "Move Choice down" }));
    const choice = nth(within(fields).getAllByRole("listitem"), 2);
    const options = within(choice).getByLabelText("Options, one per line");
    await user.clear(options);
    await user.type(options, "RCT{Enter}{Enter}Cohort");
    await user.click(screen.getByRole("button", { name: "Remove Table" }));
    await user.click(screen.getByLabelText("Two people extract each study, then reconcile"));
    await user.click(screen.getByRole("button", { name: "Save draft" }));

    const [saved] = server.calls(`PATCH ${base}/extraction-forms/${draft.id}`);
    expect(await saved?.json()).toEqual({
      name: "Trial data",
      dual: true,
      schema: {
        fields: [
          {
            key: "participants_n",
            label: "Participants (n)",
            type: "number",
            required: true,
            unit: "people",
            integer: true,
            minimum: 1,
          },
          { key: "choice", label: "Choice", type: "select", options: ["RCT", "Cohort"] },
        ],
      },
    });

    await user.click(screen.getByRole("button", { name: "Publish version 1" }));
    expect(await screen.findByText("'Arms': a table needs at least one column.")).toBeVisible();
  });

  test("a table's columns are edited in place", async () => {
    const draft = form({
      id: "00000000-0000-4000-8000-00000000f003",
      published: false,
      schema: { fields: [] },
    });
    const server = mockApi(
      routes({
        [`GET ${base}/extraction-forms`]: [draft],
        [`PATCH ${base}/extraction-forms/${draft.id}`]: draft,
      }),
    );
    const user = userEvent.setup();
    renderApp(`${page}/forms?form=${draft.id}`);

    const adding = await screen.findByRole("group", { name: "Add a field" });
    await user.click(within(adding).getByRole("button", { name: "Table" }));
    await user.click(screen.getByRole("button", { name: "Add a column" }));
    const columns = screen.getAllByLabelText("Type");
    await user.selectOptions(nth(columns, 2), "number");
    await user.type(screen.getByLabelText("Most rows"), "4");
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    const [saved] = server.calls(`PATCH ${base}/extraction-forms/${draft.id}`);
    const body = (await saved?.json()) as {
      schema: { fields: { columns: unknown[]; max_rows: number }[] };
    };
    expect(body.schema.fields[0]?.columns).toEqual([
      { key: "short_text", label: "Short text", type: "short_text" },
      { key: "short_text_2", label: "Short text", type: "number" },
    ]);
    expect(body.schema.fields[0]?.max_rows).toBe(4);
  });

  test("a published version is read, and the next version started from it", async () => {
    const server = mockApi(
      routes({
        [`POST ${base}/extraction-forms/${F1}/versions`]: form({
          id: "00000000-0000-4000-8000-00000000f004",
          version: 2,
          published: false,
        }),
      }),
    );
    const user = userEvent.setup();
    renderApp(`${page}/forms?form=${F1}`);
    expect(await screen.findByText(/Published and locked: 3 extractions use it/)).toBeVisible();
    expect(screen.getByLabelText(/Participants/)).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Start version 2" }));
    expect(server.calls(`POST ${base}/extraction-forms/${F1}/versions`)).toHaveLength(1);
  });
});

describe("consensus", () => {
  test("differences side by side, a value taken from each, and the consensus saved", async () => {
    const server = mockApi(
      routes({
        [`GET ${base}/extraction-forms/${F1}/consensus/${R1}`]: {
          record_id: R1,
          title: "Night shifts and sleep",
          label: "Okafor 2016",
          entries: [
            {
              id: "a",
              record_id: R1,
              form_id: F1,
              data: {},
              status: "submitted",
              extractor: "Ngozi Okafor",
              mine: false,
              updated_at: "2026-09-25T10:00:00Z",
            },
            {
              id: "b",
              record_id: R1,
              form_id: F1,
              data: {},
              status: "submitted",
              extractor: "Elin Lindqvist",
              mine: false,
              updated_at: "2026-09-25T10:00:00Z",
            },
          ],
          differences: [
            { path: "n", label: "Participants", values: [120, 118] },
            { path: "arms[1].mean", label: "Arms, row 1: Mean", values: [6.5, null] },
          ],
          agreed: { design: "RCT", arms: [{ arm: "Melatonin" }] },
          consensus: null,
        },
        [`PUT ${base}/extraction-forms/${F1}/consensus/${R1}`]: {
          data: {},
          resolved_by: USER.name,
          updated_at: "2026-09-25T12:00:00Z",
        },
      }),
    );
    const user = userEvent.setup();
    renderApp(`${page}/consensus`);

    const waiting = await screen.findByRole("navigation", { name: "Studies to reconcile" });
    expect(within(waiting).getByText("1 of 1 still to reconcile.")).toBeVisible();
    await user.click(within(waiting).getByRole("link", { name: /Okafor 2016/ }));
    const table = await screen.findByRole("table", {
      name: "Values the extractors gave differently",
    });
    expect(within(table).getByText("(empty)")).toBeVisible();
    expect(screen.getAllByText("Extractors differ").length).toBeGreaterThan(0);
    await user.click(
      screen.getByRole("button", { name: "Use Elin Lindqvist's value for Participants" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Use Ngozi Okafor's value for Arms, row 1: Mean" }),
    );
    await user.click(screen.getByRole("button", { name: "Save consensus" }));

    const [sent] = server.calls(`PUT ${base}/extraction-forms/${F1}/consensus/${R1}`);
    expect(await sent?.json()).toEqual({
      data: { design: "RCT", n: 118, arms: [{ arm: "Melatonin", mean: 6.5 }] },
    });
  });

  test("nothing to reconcile, and agreement on every field", async () => {
    mockApi(
      routes({ [`GET ${base}/extraction-forms/${F1}/studies`]: [{ ...STUDY, submitted: 1 }] }),
    );
    const { unmount } = renderApp(`${page}/consensus`);
    expect(await screen.findByText(/Nothing to reconcile/)).toBeVisible();
    unmount();

    mockApi(
      routes({
        [`GET ${base}/extraction-forms/${F1}/consensus/${R1}`]: {
          record_id: R1,
          title: null,
          label: "Okafor 2016",
          entries: [],
          differences: [],
          agreed: {},
          consensus: {
            data: { design: "RCT" },
            resolved_by: null,
            updated_at: "2026-09-25T12:00:00Z",
          },
        },
      }),
    );
    renderApp(`${page}/consensus?form=${F1}&study=${R1}`);
    expect(await screen.findByText("The extractions agree on every field.")).toBeVisible();
    expect(screen.getByText(/reconciled by a former member/)).toBeVisible();
    expect(screen.getByLabelText(/Study design/)).toHaveValue("RCT");
  });
});

describe("exporting extracted data", () => {
  test("a form's data, long or wide", async () => {
    let asked = false;
    const job = {
      id: "x1",
      kind: "extraction",
      format: "xlsx",
      status: "queued",
      filename: null,
      size_bytes: null,
      rows: null,
      problem: null,
      created_at: new Date().toISOString(),
      expires_at: null,
    };
    const server = mockApi(
      routes({
        [`GET ${base}/exports`]: () => (asked ? [job] : []),
        [`POST ${base}/exports`]: () => {
          asked = true;
          return job;
        },
      }),
    );
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/report/exports`);

    await user.click(await screen.findByText("Extracted data"));
    screen.getByLabelText("Layout").focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("option", { name: /^Long/ }));
    screen.getByLabelText("Which data").focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("option", { name: /^All/ }));
    screen.getByLabelText("Format").focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("option", { name: "Excel (XLSX)" }));
    await user.click(screen.getByRole("button", { name: "Make the file" }));

    const [sent] = server.calls(`POST ${base}/exports`);
    expect(await sent?.json()).toEqual({
      kind: "extraction",
      format: "xlsx",
      extraction: { form_id: F1, layout: "long", which: "all" },
    });
    expect((await screen.findAllByText(/Extracted data \(XLSX\)/))[0]).toBeVisible();
  });
});
