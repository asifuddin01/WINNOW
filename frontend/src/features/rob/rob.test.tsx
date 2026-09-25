import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import type { Project } from "@/api/projects";
import { robSearch } from "@/lib/search";
import { PROJECT, USER, mockApi, problemResponse, projectRoutes } from "@/test/api";
import { renderApp } from "@/test/render-app";

const base = `/api/v1/projects/${PROJECT.id}`;
const page = `/p/${PROJECT.id}/rob`;
const R1 = "00000000-0000-4000-8000-000000000001";
const R2 = "00000000-0000-4000-8000-000000000002";

const JUDGEMENTS = [
  { key: "low", label: "Low risk" },
  { key: "some_concerns", label: "Some concerns" },
  { key: "high", label: "High risk" },
];

function domain(key: string, name: string) {
  return {
    key,
    name,
    questions: [
      {
        key: `${key}_q1`,
        prompt: `${name}: first question?`,
        answers: ["yes", "probably_no", "no_information"],
      },
    ],
    axes: [{ key: "risk_of_bias", name: "Risk of bias", judgements: JUDGEMENTS }],
  };
}

const ROB2 = {
  key: "rob2",
  name: "RoB 2",
  version: "22 August 2019",
  source_url: "https://www.riskofbias.info/",
  note: "",
  variants: [
    {
      key: "parallel_assignment",
      name: "Individually randomised, parallel group",
      domains: [
        domain("randomisation", "Randomisation"),
        domain("missing", "Missing outcome data"),
      ],
    },
  ],
};

const QUADAS = {
  key: "quadas2",
  name: "QUADAS-2",
  version: "2011",
  source_url: "https://www.bristol.ac.uk/",
  note: "",
  variants: [
    {
      key: "diagnostic_accuracy",
      name: "Diagnostic accuracy",
      domains: [
        {
          key: "patient_selection",
          name: "Patient selection",
          questions: [],
          axes: [
            {
              key: "risk_of_bias",
              name: "Risk of bias",
              judgements: [{ key: "low", label: "Low risk" }],
            },
            {
              key: "applicability",
              name: "Applicability",
              judgements: [{ key: "low", label: "Low concern" }],
            },
          ],
        },
      ],
    },
  ],
};

const STUDIES = [
  {
    record_id: R1,
    label: "Okafor 2016",
    title: "Night shifts",
    mine: "submitted",
    submitted: 2,
    final_chosen: false,
  },
  {
    record_id: R2,
    label: "Lindqvist 2017",
    title: "Rosters",
    mine: "none",
    submitted: 0,
    final_chosen: false,
  },
];

function assessment(extra: Record<string, unknown> = {}) {
  return {
    id: "a1",
    record_id: R1,
    tool_key: "rob2",
    tool_version: "22 August 2019",
    variant_key: "parallel_assignment",
    answers: { randomisation: { randomisation_q1: "yes" } },
    judgements: {
      randomisation: { risk_of_bias: "low" },
      missing: { risk_of_bias: "some_concerns" },
    },
    support: { randomisation: "Computer-generated sequence." },
    overall: "some_concerns",
    status: "submitted",
    final: false,
    assessor: USER.name,
    mine: true,
    updated_at: "2026-09-25T10:00:00Z",
    ...extra,
  };
}

function routes(extra: Record<string, unknown> = {}, project: Project = PROJECT) {
  return {
    "GET /api/v1/auth/me": USER,
    ...projectRoutes(project),
    [`GET ${base}/rob/tools`]: [ROB2, QUADAS],
    [`GET ${base}/rob/studies`]: STUDIES,
    [`GET ${base}/rob/summary`]: {
      tool_key: "rob2",
      tool_name: "RoB 2",
      tool_version: "22 August 2019",
      variants: [
        {
          variant_key: "parallel_assignment",
          variant_name: "Individually randomised, parallel group",
          domains: [],
          studies: [
            {
              record_id: R1,
              label: "Okafor 2016",
              cells: { "randomisation.risk_of_bias": "low", "missing.risk_of_bias": "high" },
              overall: "high",
            },
          ],
        },
      ],
      awaiting_final: [R1],
      own_only: false,
    },
    ...extra,
  };
}

describe("risk of bias", () => {
  test("the studies, their states, and the review's plots with their numbers as a table", async () => {
    mockApi(routes());
    const user = userEvent.setup();
    renderApp(page);

    const studies = await screen.findByRole("navigation", { name: "Studies" });
    expect(within(studies).getByText("You have submitted 1 of 2.")).toBeVisible();
    expect(within(studies).getByText("2 to reconcile")).toBeVisible();
    expect(within(studies).getByText("Not started")).toBeVisible();
    expect(await screen.findByText(/1 study was assessed by more than one person/)).toBeVisible();

    const light = await screen.findByRole("img", { name: /Traffic-light plot of 1 studies/ });
    expect(light.getAttribute("src")).toContain("summary.svg?tool=rob2&plot=traffic-light");
    expect(screen.getAllByRole("link", { name: "PNG" })[0]).toHaveAttribute(
      "href",
      `${base}/rob/summary.png?tool=rob2&plot=traffic-light&variant=parallel_assignment`,
    );
    await user.click(screen.getByText("The judgements as a table"));
    const table = screen.getByRole("table", { name: "Judgements by study and domain" });
    expect(within(table).getByRole("row", { name: /Okafor 2016/ })).toHaveTextContent(
      /Okafor 2016.*Low risk.*High risk.*High risk/,
    );
  });

  test("assessing a study: answers, judgements, support, then submit or keep a draft", async () => {
    const server = mockApi(
      routes({
        [`GET ${base}/rob/${R2}`]: {
          record_id: R2,
          title: "Rotating rosters and fatigue",
          assessments: [],
        },
        [`PUT ${base}/rob/${R2}`]: assessment({ record_id: R2, status: "draft" }),
      }),
    );
    const user = userEvent.setup();
    renderApp(page);

    await user.click(await screen.findByRole("link", { name: /Lindqvist 2017/ }));
    expect(
      await screen.findByRole("heading", { name: "Rotating rosters and fatigue" }),
    ).toBeVisible();
    const first = screen.getByRole("group", { name: "Randomisation" });
    await user.click(within(first).getByRole("radio", { name: "Probably no" }));
    await user.click(within(first).getByRole("radio", { name: "Low risk" }));
    await user.type(within(first).getByLabelText("Support for the judgement"), "Sealed envelopes.");
    await user.click(screen.getByRole("button", { name: "Save as draft" }));

    const [draft] = server.calls(`PUT ${base}/rob/${R2}`);
    expect(await draft?.json()).toEqual({
      tool_key: "rob2",
      variant_key: "parallel_assignment",
      answers: { randomisation: { randomisation_q1: "probably_no" } },
      judgements: { randomisation: { risk_of_bias: "low" } },
      support: { randomisation: "Sealed envelopes." },
      overall: null,
      status: "draft",
    });

    const second = screen.getByRole("group", { name: "Missing outcome data" });
    await user.click(within(second).getByRole("radio", { name: "High risk" }));
    screen.getByLabelText("Overall judgement").focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("option", { name: "High risk" }));
    await user.click(screen.getByRole("button", { name: "Submit" }));
    const submitted = server.calls(`PUT ${base}/rob/${R2}`)[1];
    expect(await submitted?.json()).toMatchObject({
      judgements: { randomisation: { risk_of_bias: "low" }, missing: { risk_of_bias: "high" } },
      overall: "high",
      status: "submitted",
    });
  });

  test("an incomplete submission is explained by the server's words", async () => {
    mockApi(
      routes({
        [`GET ${base}/rob/${R2}`]: { record_id: R2, title: "Rosters", assessments: [] },
        [`PUT ${base}/rob/${R2}`]: () =>
          problemResponse(422, {
            title: "Invalid",
            code: "invalid_assessment",
            detail: "Missing outcome data: Risk of bias needs a judgement.",
          }),
      }),
    );
    const user = userEvent.setup();
    renderApp(page);
    await user.click(await screen.findByRole("link", { name: /Lindqvist 2017/ }));
    await user.click(await screen.findByRole("button", { name: "Submit" }));
    expect(
      await screen.findAllByText("Missing outcome data: Risk of bias needs a judgement."),
    ).not.toHaveLength(0);
  });

  test("everyone's assessments, and choosing the final one", async () => {
    const server = mockApi(
      routes({
        [`GET ${base}/rob/${R1}`]: {
          record_id: R1,
          title: "Night shifts and sleep in nurses",
          assessments: [
            assessment(),
            assessment({ id: "a2", mine: false, assessor: "Grace Hopper", overall: "low" }),
            assessment({ id: "a3", mine: false, assessor: null, status: "draft" }),
          ],
        },
        [`POST ${base}/rob/${R1}/final`]: assessment({ id: "a2", final: true }),
        [`DELETE ${base}/rob/${R1}`]: () => new Response(null, { status: 204 }),
      }),
    );
    const user = userEvent.setup();
    renderApp(page);

    await user.click(await screen.findByRole("link", { name: /Okafor 2016/ }));
    // My own assessment fills the form.
    const first = await screen.findByRole("group", { name: "Randomisation" });
    expect(within(first).getByRole("radio", { name: "Yes" })).toBeChecked();
    expect(within(first).getByLabelText("Support for the judgement")).toHaveValue(
      "Computer-generated sequence.",
    );
    const everyone = screen.getByRole("region", { name: "Everyone's assessments" });
    expect(within(everyone).getByText("A former member")).toBeVisible();
    expect(within(everyone).getAllByRole("button", { name: "Use as final" })).toHaveLength(1);
    await user.click(within(everyone).getByRole("button", { name: "Use as final" }));
    const [chosen] = server.calls(`POST ${base}/rob/${R1}/final`);
    expect(await chosen?.json()).toEqual({ assessment_id: "a2" });

    await user.click(screen.getByRole("button", { name: "Delete my assessment" }));
    expect(server.calls(`DELETE ${base}/rob/${R1}`)[0]?.url).toContain("tool=rob2");
  });

  test("two axes are judged apart (QUADAS-2), and a viewer can only read", async () => {
    const viewer: Project = {
      ...PROJECT,
      membership: { ...PROJECT.membership, role: "viewer" },
      permissions: ["view", "export"],
    };
    mockApi(
      routes(
        {
          [`GET ${base}/rob/${R1}`]: {
            record_id: R1,
            title: "Night shifts",
            assessments: [
              assessment({
                id: "q1",
                tool_key: "quadas2",
                variant_key: "diagnostic_accuracy",
                mine: false,
                assessor: "Grace Hopper",
                judgements: { patient_selection: { risk_of_bias: "low", applicability: "low" } },
              }),
            ],
          },
        },
        viewer,
      ),
    );
    renderApp(`${page}?tool=quadas2`);

    await userEvent.setup().click(await screen.findByRole("link", { name: /Okafor 2016/ }));
    const everyone = await screen.findByRole("region", { name: "Everyone's assessments" });
    expect(within(everyone).getByText("Patient selection: Risk of bias")).toBeVisible();
    expect(within(everyone).getByText("Patient selection: Applicability")).toBeVisible();
    expect(within(everyone).getByText("Low concern")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Submit" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Use as final" })).toBeNull();
  });

  test("a study not included at full text cannot be assessed; no studies, no plots", async () => {
    mockApi(
      routes({
        [`GET ${base}/rob/studies`]: [],
        [`GET ${base}/rob/00000000-0000-4000-8000-000000000009`]: () =>
          problemResponse(409, { title: "Conflict", detail: "Not included." }),
      }),
    );
    renderApp(`${page}?study=00000000-0000-4000-8000-000000000009`);
    expect(await screen.findByText(/This study cannot be assessed/)).toBeVisible();
    expect(screen.getByText(/No studies yet/)).toBeVisible();
  });

  test("the page's address keeps only a known tool and a real id", () => {
    expect(robSearch({ tool: "nos", study: "00000000-0000-4000-8000-000000000009" })).toEqual({
      tool: "nos",
      study: "00000000-0000-4000-8000-000000000009",
    });
    expect(robSearch({ tool: "grade", study: "../etc" })).toEqual({});
  });
});
