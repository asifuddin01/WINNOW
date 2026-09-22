import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import type { Member, Project } from "@/api/projects";
import { OWNER_MEMBER, PROJECT, USER, json, mockApi, projectRoutes } from "@/test/api";
import { renderApp } from "@/test/render-app";

const signedIn = { "GET /api/v1/auth/me": USER };
const base = `/api/v1/projects/${PROJECT.id}`;

const REASONS = [
  { id: "r1", label: "Wrong population", stage: "both" as const, position: 0 },
  { id: "r2", label: "Wrong outcome", stage: "both" as const, position: 1 },
];

describe("exclusion reasons", () => {
  test("a reason is added, moved and deleted", async () => {
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`GET ${base}/exclusion-reasons`]: REASONS,
      [`POST ${base}/exclusion-reasons`]: {
        id: "r3",
        label: "Protocol only",
        stage: "title_abstract",
        position: 2,
      },
      [`PATCH ${base}/exclusion-reasons/r2`]: { ...REASONS[1], position: 0 },
      [`DELETE ${base}/exclusion-reasons/r1`]: () => json(null, 204),
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/settings/reasons`);

    await user.type(await screen.findByLabelText("New reason"), "Protocol only");
    await user.click(screen.getByRole("button", { name: "Add reason" }));
    expect(await server.calls(`POST ${base}/exclusion-reasons`)[0]?.json()).toEqual({
      label: "Protocol only",
      stage: "both",
    });

    await user.click(screen.getByRole("button", { name: "Move “Wrong outcome” up" }));
    expect(await server.calls(`PATCH ${base}/exclusion-reasons/r2`)[0]?.json()).toEqual({
      position: 0,
    });

    await user.click(screen.getByRole("button", { name: "Delete “Wrong population”" }));
    expect(server.calls(`DELETE ${base}/exclusion-reasons/r1`)).toHaveLength(1);
  });
});

describe("labels", () => {
  test("a label is added with a colour and deleted", async () => {
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`GET ${base}/labels`]: [{ id: "l1", name: "Key paper", color: "violet" }],
      [`POST ${base}/labels`]: { id: "l2", name: "Check with Sara", color: "green" },
      [`DELETE ${base}/labels/l1`]: () => json(null, 204),
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/settings/labels`);

    expect(await screen.findByText("Key paper")).toBeVisible();
    await user.type(screen.getByLabelText("New label"), "Check with Sara");
    await user.click(screen.getByRole("radio", { name: "Green" }));
    await user.click(screen.getByRole("button", { name: "Add label" }));
    expect(await server.calls(`POST ${base}/labels`)[0]?.json()).toEqual({
      name: "Check with Sara",
      color: "green",
    });

    await user.click(screen.getByRole("button", { name: "Delete label “Key paper”" }));
    expect(server.calls(`DELETE ${base}/labels/l1`)).toHaveLength(1);
  });
});

describe("the general settings page", () => {
  test("the basics are saved", async () => {
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`PATCH ${base}`]: { ...PROJECT, title: "Shift work and sleep" },
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/settings`);

    const title = await screen.findByLabelText("Title");
    await user.clear(title);
    await user.type(title, "Shift work and sleep");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await server.calls(`PATCH ${base}`)[0]?.json()).toMatchObject({
      title: "Shift work and sleep",
      description: null,
    });
  });

  test("the setup can be copied into a new review", async () => {
    const copy: Project = { ...PROJECT, id: "0192f0c1-0000-7000-8000-00000000ccc1", title: "Copy" };
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`GET /api/v1/projects/${copy.id}`]: copy,
      [`GET /api/v1/projects/${copy.id}/members`]: { items: [OWNER_MEMBER], next_cursor: null },
      [`GET /api/v1/projects/${copy.id}/criteria`]: [],
      [`GET /api/v1/projects/${copy.id}/keyword-groups`]: [],
      [`GET /api/v1/projects/${copy.id}/exclusion-reasons`]: [],
      [`GET /api/v1/projects/${copy.id}/labels`]: [],
      [`POST ${base}/duplicate-setup`]: copy,
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/settings`);

    await user.click(await screen.findByRole("button", { name: "Copy setup" }));
    expect(await server.calls(`POST ${base}/duplicate-setup`)[0]?.json()).toEqual({
      title: `Copy of ${PROJECT.title}`,
    });
    expect(await screen.findByRole("heading", { level: 1, name: "Copy" })).toBeVisible();
  });

  test("archiving and restoring a review", async () => {
    const archived: Project = { ...PROJECT, status: "archived" };
    const server = mockApi({ ...signedIn, ...projectRoutes(), [`PATCH ${base}`]: archived });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/settings`);

    await user.click(await screen.findByRole("button", { name: "Archive" }));
    expect(await server.calls(`PATCH ${base}`)[0]?.json()).toEqual({ status: "archived" });
  });

  test("a reviewer leaves the review", async () => {
    const asReviewer: Project = {
      ...PROJECT,
      membership: { ...PROJECT.membership, role: "reviewer" },
      permissions: ["view", "screen", "export"],
    };
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(asReviewer),
      [`DELETE ${base}/membership`]: () => json(null, 204),
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/settings`);

    await user.click(await screen.findByRole("button", { name: "Leave" }));
    const dialog = within(await screen.findByRole("alertdialog"));
    await user.click(dialog.getByRole("button", { name: "Leave" }));
    expect(server.calls(`DELETE ${base}/membership`)).toHaveLength(1);
    expect(await screen.findByRole("heading", { level: 1, name: "My reviews" })).toBeVisible();
  });

  test("ownership is handed to another member", async () => {
    const grace: Member = {
      user: { id: "0192f0c1-0000-7000-8000-00000000bbb1", name: "Grace Hopper", email: "g@x.org" },
      role: "admin",
      can_resolve_conflicts: false,
      stages: ["title_abstract", "full_text"],
      joined_at: "2026-09-21T10:00:00Z",
    };
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(PROJECT, [OWNER_MEMBER, grace]),
      [`POST ${base}/transfer`]: { ...PROJECT, owner: grace.user },
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/settings`);

    (await screen.findByLabelText("New owner")).focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("option", { name: "Grace Hopper" }));
    await user.click(screen.getByRole("button", { name: "Transfer" }));
    const dialog = within(await screen.findByRole("alertdialog"));
    await user.click(dialog.getByRole("button", { name: "Transfer" }));

    expect(await server.calls(`POST ${base}/transfer`)[0]?.json()).toEqual({
      user_id: grace.user.id,
    });
  });
});

describe("blind screening", () => {
  test("an owner can choose to stay blind as well", async () => {
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`PATCH ${base}/membership`]: {
        role: "owner",
        can_resolve_conflicts: false,
        stages: ["title_abstract", "full_text"],
        keep_blind: false,
      },
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/settings/screening`);

    await user.click(await screen.findByLabelText("Keep me blind too"));
    expect(await server.calls(`PATCH ${base}/membership`)[0]?.json()).toEqual({
      keep_blind: false,
    });
  });

  test("it is not offered when blind screening is off", async () => {
    const open: Project = {
      ...PROJECT,
      settings: { ...PROJECT.settings, blind_mode: false },
    };
    mockApi({ ...signedIn, ...projectRoutes(open) });
    renderApp(`/p/${PROJECT.id}/settings/screening`);

    expect(await screen.findByLabelText("Blind screening")).not.toBeChecked();
    expect(screen.queryByLabelText("Keep me blind too")).toBeNull();
  });
});

describe("more of the screening settings", () => {
  test("several settings change together, and can be discarded", async () => {
    const server = mockApi({ ...signedIn, ...projectRoutes(), [`PATCH ${base}`]: PROJECT });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/settings/screening`);

    await user.click(await screen.findByLabelText("Highlight keywords while screening"));
    await user.click(
      screen.getByLabelText("Require a reason when excluding at title and abstract"),
    );

    // A number of reviewers, through the keyboard: Radix selects ignore jsdom clicks.
    screen.getByLabelText("Reviewers per record: title and abstract").focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("option", { name: "1 reviewer" }));

    const stop = screen.getByLabelText("After this many excludes in a row");
    await user.clear(stop);
    await user.type(stop, "150");

    await user.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await server.calls(`PATCH ${base}`)[0]?.json()).toMatchObject({
      settings: {
        highlight_keywords: false,
        require_reason_on_exclude_ta: true,
        reviewers_per_record_ta: 1,
        stopping_rule: { type: "consecutive_excludes", n: 150 },
      },
    });

    await user.click(screen.getByLabelText("Blind screening"));
    await user.click(screen.getByRole("button", { name: "Discard changes" }));
    expect(screen.getByLabelText("Blind screening")).toBeChecked();
  });
});

describe("keyword groups", () => {
  test("a group is created, a term removed and the group deleted", async () => {
    const group = {
      id: "g1",
      name: "Population",
      color: "teal" as const,
      kind: "include" as const,
      keywords: [{ id: "k1", group_id: "g1", term: "nurses", is_regex: false, whole_word: true }],
    };
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`GET ${base}/keyword-groups`]: [group],
      [`POST ${base}/keyword-groups`]: { ...group, id: "g2", name: "Outcome" },
      [`DELETE ${base}/keywords/k1`]: () => json(null, 204),
      [`DELETE ${base}/keyword-groups/g1`]: () => json(null, 204),
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/settings/keywords`);

    await user.type(await screen.findByLabelText("New keyword group"), "Outcome");
    await user.click(screen.getByRole("button", { name: "Add group" }));
    expect(await server.calls(`POST ${base}/keyword-groups`)[0]?.json()).toEqual({
      name: "Outcome",
      kind: "include",
      color: "amber",
    });

    await user.click(screen.getByRole("button", { name: "Remove “nurses” from Population" }));
    expect(server.calls(`DELETE ${base}/keywords/k1`)).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Delete group Population" }));
    expect(server.calls(`DELETE ${base}/keyword-groups/g1`)).toHaveLength(1);
  });
});

describe("criteria", () => {
  test("the text of a criterion is edited in place", async () => {
    const criterion = { id: "c1", kind: "inclusion" as const, text: "Adults", position: 0 };
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`GET ${base}/criteria`]: [criterion],
      [`PATCH ${base}/criteria/c1`]: { ...criterion, text: "Adults over 18" },
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/settings/criteria`);

    await user.click(await screen.findByRole("button", { name: "Edit “Adults”" }));
    const box = screen.getByLabelText("Criterion");
    await user.clear(box);
    await user.type(box, "Adults over 18");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await server.calls(`PATCH ${base}/criteria/c1`)[0]?.json()).toEqual({
      text: "Adults over 18",
    });
  });
});

describe("pending invitations", () => {
  test("an invitation can be withdrawn", async () => {
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(),
      [`GET ${base}/invites`]: [
        {
          id: "i1",
          email: "grace@x.org",
          role: "reviewer",
          invited_by: USER.name,
          created_at: "2026-09-22T10:00:00Z",
          expires_at: "2026-09-29T10:00:00Z",
          expired: false,
        },
      ],
      [`DELETE ${base}/invites/i1`]: () => json(null, 204),
    });
    const user = userEvent.setup();
    renderApp(`/p/${PROJECT.id}/settings/team`);

    expect(await screen.findByText("Invited, not joined yet")).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: "Withdraw the invitation to grace@x.org" }),
    );
    expect(server.calls(`DELETE ${base}/invites/i1`)).toHaveLength(1);
  });
});
