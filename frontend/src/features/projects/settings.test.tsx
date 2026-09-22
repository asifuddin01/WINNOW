import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import type { Member, Project } from "@/api/projects";
import {
  OPTIONS,
  OWNER_MEMBER,
  PROJECT,
  USER,
  json,
  mockApi,
  problemResponse,
  projectRoutes,
} from "@/test/api";
import { renderApp } from "@/test/render-app";

const signedIn = { "GET /api/v1/auth/me": USER };
const base = `/api/v1/projects/${PROJECT.id}`;

const GRACE: Member = {
  user: { id: "0192f0c1-0000-7000-8000-00000000bbb1", name: "Grace Hopper", email: "grace@x.org" },
  role: "reviewer",
  can_resolve_conflicts: false,
  stages: ["title_abstract", "full_text"],
  joined_at: "2026-09-21T10:00:00Z",
};

/** The same review seen by someone who may only read it. */
const asReviewer: Project = {
  ...PROJECT,
  membership: { ...PROJECT.membership, role: "reviewer" },
  permissions: ["view", "screen", "export"],
  member_count: 2,
};

describe("criteria settings", () => {
  test("an admin edits and reorders; a reviewer only reads", async () => {
    const criteria = [
      { id: "c1", kind: "inclusion" as const, text: "Adults over 18", position: 0 },
      { id: "c2", kind: "inclusion" as const, text: "Randomised trials", position: 1 },
    ];
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`GET ${base}/criteria`]: criteria,
      [`PATCH ${base}/criteria/c2`]: { ...criteria[1], position: 0 },
      [`DELETE ${base}/criteria/c1`]: () => json(null, 204),
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/settings/criteria`);

    expect(await screen.findByText("Adults over 18")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Move “Randomised trials” up" }));
    expect(await server.calls(`PATCH ${base}/criteria/c2`)[0]?.json()).toEqual({ position: 0 });

    await user.click(screen.getByRole("button", { name: "Delete “Adults over 18”" }));
    expect(server.calls(`DELETE ${base}/criteria/c1`)).toHaveLength(1);
  });

  test("a reviewer sees the criteria without the controls", async () => {
    mockApi({
      ...signedIn,
      ...projectRoutes(asReviewer),
      [`GET ${base}/criteria`]: [
        { id: "c1", kind: "inclusion", text: "Adults over 18", position: 0 },
      ],
    });
    renderApp(`/p/${PROJECT.id}/settings/criteria`);

    expect(await screen.findByText("Adults over 18")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Add inclusion criterion" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete “Adults over 18”" })).toBeNull();
  });
});

describe("keywords settings", () => {
  test("terms are added to a group in one go", async () => {
    const group = {
      id: "g1",
      name: "Population",
      color: "teal" as const,
      kind: "include" as const,
      keywords: [],
    };
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`GET ${base}/keyword-groups`]: [group],
      [`POST ${base}/keywords`]: group,
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/settings/keywords`);

    await user.type(
      await screen.findByLabelText("Terms for Population"),
      "nurses, nursing staff\nRN",
    );
    await user.click(screen.getByLabelText("Whole words only"));
    await user.click(screen.getByRole("button", { name: "Add to Population" }));

    expect(await server.calls(`POST ${base}/keywords`)[0]?.json()).toEqual({
      group_id: "g1",
      terms: ["nurses", "nursing staff", "RN"],
      is_regex: false,
      whole_word: false,
    });
  });

  test("the server's complaint about a pattern is shown", async () => {
    const group = {
      id: "g1",
      name: "Population",
      color: "teal" as const,
      kind: "include" as const,
      keywords: [],
    };
    mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`GET ${base}/keyword-groups`]: [group],
      [`POST ${base}/keywords`]: () =>
        problemResponse(422, {
          title: "Unprocessable Entity",
          code: "invalid_pattern",
          detail: "“(a+)+”: A repeated group cannot contain a repeat or alternatives.",
        }),
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/settings/keywords`);

    await user.type(await screen.findByLabelText("Terms for Population"), "(a+)+");
    await user.click(screen.getByLabelText("These are patterns"));
    await user.click(screen.getByRole("button", { name: "Add to Population" }));
    expect(await screen.findByText(/A repeated group cannot contain a repeat/)).toBeVisible();
  });
});

describe("the team", () => {
  test("an owner invites someone and gets a link when email is off", async () => {
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(),
      "GET /api/v1/auth/options": { ...OPTIONS, email_enabled: false },
      [`POST ${base}/invites`]: {
        id: "i1",
        email: "grace@x.org",
        role: "reviewer",
        invited_by: USER.name,
        created_at: "2026-09-22T10:00:00Z",
        expires_at: "2026-09-29T10:00:00Z",
        expired: false,
        link: "https://winnow.test/invite/tok-en",
        emailed: false,
      },
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/settings/team`);

    await user.type(await screen.findByLabelText("Invite by email"), "grace@x.org");
    await user.click(screen.getByRole("button", { name: "Send invitation" }));

    expect(await server.calls(`POST ${base}/invites`)[0]?.json()).toEqual({
      email: "grace@x.org",
      role: "reviewer",
    });
    expect(await screen.findByText("https://winnow.test/invite/tok-en")).toBeVisible();
    expect(screen.getByText(/pass this link on yourself/)).toBeVisible();
  });

  test("a role change is sent, and the owner's role cannot be touched", async () => {
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(PROJECT, [OWNER_MEMBER, GRACE]),
      [`PATCH ${base}/members/${GRACE.user.id}`]: { ...GRACE, role: "admin" },
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/settings/team`);

    expect((await screen.findAllByText("Grace Hopper"))[0]).toBeVisible();
    // The owner (me) is shown as a badge, with no way to change it.
    expect(screen.queryByLabelText(`Role for ${USER.name}`)).toBeNull();

    screen.getByLabelText("Role for Grace Hopper").focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("option", { name: /Admin/ }));
    expect(await server.calls(`PATCH ${base}/members/${GRACE.user.id}`)[0]?.json()).toEqual({
      role: "admin",
    });
  });

  test("removing someone asks first", async () => {
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(PROJECT, [OWNER_MEMBER, GRACE]),
      [`DELETE ${base}/members/${GRACE.user.id}`]: () => json(null, 204),
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/settings/team`);

    await user.click(await screen.findByRole("button", { name: "Remove Grace Hopper" }));
    const dialog = within(await screen.findByRole("alertdialog"));
    expect(dialog.getByText("Remove Grace Hopper?")).toBeVisible();
    await user.click(dialog.getByRole("button", { name: "Remove" }));
    expect(server.calls(`DELETE ${base}/members/${GRACE.user.id}`)).toHaveLength(1);
  });

  test("a reviewer sees the team but cannot invite", async () => {
    mockApi({ ...signedIn, ...projectRoutes(asReviewer, [OWNER_MEMBER, GRACE]) });
    renderApp(`/p/${PROJECT.id}/settings/team`);

    expect((await screen.findAllByText("Grace Hopper"))[0]).toBeVisible();
    expect(screen.queryByLabelText("Invite by email")).toBeNull();
    expect(screen.queryByRole("button", { name: "Remove Grace Hopper" })).toBeNull();
  });
});

describe("screening settings", () => {
  test("changes are saved together", async () => {
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`PATCH ${base}`]: {
        ...PROJECT,
        settings: { ...PROJECT.settings, blind_mode: false },
      },
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/settings/screening`);

    const save = await screen.findByRole("button", { name: "Save settings" });
    expect(save).toBeDisabled();
    await user.click(screen.getByLabelText("Blind screening"));
    expect(save).toBeEnabled();
    await user.click(save);

    expect(await server.calls(`PATCH ${base}`)[0]?.json()).toMatchObject({
      settings: { blind_mode: false },
    });
  });

  test("AI suggestions stay off when the instance has no provider", async () => {
    mockApi({ ...signedIn, ...projectRoutes() });
    renderApp(`/p/${PROJECT.id}/settings/screening`);
    expect(await screen.findByLabelText("AI suggestions with reasons")).toBeDisabled();
    expect(screen.getByText(/no AI provider set up/)).toBeVisible();
  });
});

describe("the danger zone", () => {
  test("deleting asks for the review's title", async () => {
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`DELETE ${base}`]: () => json(null, 204),
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/settings`);

    await user.click(await screen.findByRole("button", { name: "Delete review" }));
    const dialog = within(await screen.findByRole("alertdialog"));
    const confirm = dialog.getByRole("button", { name: "Delete review" });
    expect(confirm).toBeDisabled();

    await user.type(dialog.getByLabelText(/to confirm/), PROJECT.title);
    expect(confirm).toBeEnabled();
    await user.click(confirm);
    expect(server.calls(`DELETE ${base}`)).toHaveLength(1);
  });

  test("a reviewer can leave but cannot delete", async () => {
    mockApi({ ...signedIn, ...projectRoutes(asReviewer, [OWNER_MEMBER, GRACE]) });
    renderApp(`/p/${PROJECT.id}/settings`);

    expect(await screen.findByRole("button", { name: "Leave" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Delete review" })).toBeNull();
    // The basics are read-only too.
    expect(screen.queryByLabelText("Title")).toBeNull();
    expect(screen.getByText(String(PROJECT.research_question))).toBeVisible();
  });
});
