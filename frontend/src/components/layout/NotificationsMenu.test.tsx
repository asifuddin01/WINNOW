import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import type { Notice } from "@/api/notifications";
import { describeNotice } from "@/features/notifications/wording";
import { PROJECT, USER, mockApi, projectRoutes } from "@/test/api";
import { renderApp } from "@/test/render-app";

function notice(kind: Notice["kind"], extra: Partial<Notice> = {}): Notice {
  return {
    id: `n-${kind}`,
    kind,
    project_id: PROJECT.id,
    count: 1,
    data: { project_title: PROJECT.title, by: "Grace Hopper" },
    read: false,
    created_at: "2026-09-25T09:00:00Z",
    updated_at: new Date().toISOString(),
    ...extra,
  };
}

describe("notice wording", () => {
  test("each kind says what happened and where it leads", () => {
    expect(describeNotice(notice("conflicts", { count: 3 }))).toEqual({
      text: `3 new conflicts to resolve in ${PROJECT.title}`,
      to: `/p/${PROJECT.id}/conflicts`,
    });
    expect(describeNotice(notice("conflicts", { project_id: null })).to).toBeNull();
    expect(describeNotice(notice("invite", { project_id: null })).text).toBe(
      `Grace Hopper invited you to ${PROJECT.title}. Accept from the invitation email.`,
    );
    expect(
      describeNotice(
        notice("mention", {
          data: { project_title: "R", by: "Hedy", excerpt: "@Ada see this", record_id: "r1" },
        }),
      ),
    ).toEqual({
      text: "Hedy mentioned you in R: “@Ada see this”",
      to: `/p/${PROJECT.id}/records?record=r1`,
    });
    expect(
      describeNotice(
        notice("import_finished", {
          data: { project_title: "R", filename: "a.ris", imported: 1204 },
        }),
      ).text,
    ).toBe("Your import of a.ris into R finished: 1,204 records");
    expect(describeNotice(notice("import_failed", { data: { filename: "b.ris" } })).text).toBe(
      "Your import of b.ris into a review failed",
    );
  });
});

describe("the bell", () => {
  test("shows the unread count; a notice opens where it points and is marked read", async () => {
    let unread = 2;
    const server = mockApi({
      "GET /api/v1/auth/me": USER,
      ...projectRoutes(),
      "GET /api/v1/notifications/unread": () => ({ unread }),
      "GET /api/v1/notifications": () => ({
        items: [
          notice("conflicts", { count: 2 }),
          notice("invite", { project_id: null, read: true }),
        ],
        next_cursor: null,
        unread,
      }),
      "POST /api/v1/notifications/n-conflicts/read": () => {
        unread = 1;
        return new Response(null, { status: 204 });
      },
      "POST /api/v1/notifications/read-all": () => {
        unread = 0;
        return new Response(null, { status: 204 });
      },
    });
    const user = userEvent.setup();
    const { router } = renderApp("/");

    const bell = await screen.findByRole("button", { name: "Notifications, 2 unread" });
    await user.click(bell);
    const menu = await screen.findByRole("menu");
    const conflict = within(menu).getByRole("menuitem", { name: /2 new conflicts to resolve/ });
    expect(conflict).toHaveTextContent("(unread)");
    expect(within(menu).getByRole("menuitem", { name: /invited you/ })).not.toHaveTextContent(
      "(unread)",
    );
    await user.click(conflict);
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/p/${PROJECT.id}/conflicts`);
    });
    expect(server.calls("POST /api/v1/notifications/n-conflicts/read")).toHaveLength(1);
    // Let the menu finish closing, or Radix's shared layer state outlives it.
    await waitFor(() => {
      expect(screen.queryByRole("menu")).toBeNull();
    });
    (await screen.findByRole("button", { name: "Notifications, 1 unread" })).focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("menuitem", { name: "Mark all as read" }));
    expect(await screen.findByRole("button", { name: "Notifications" })).toBeVisible();
    // Marking all read keeps the menu open, so the notices can be seen turning read.
    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("menu")).toBeNull();
    });
  });

  test("nothing yet, and the digest switch on the account page", async () => {
    let digest = false;
    const server = mockApi({
      "GET /api/v1/auth/me": USER,
      "GET /api/v1/auth/sessions": [],
      "GET /api/v1/notifications/unread": { unread: 0 },
      "GET /api/v1/notifications": { items: [], next_cursor: null, unread: 0 },
      "GET /api/v1/notifications/settings": () => ({ email_digest: digest }),
      "PUT /api/v1/notifications/settings": (request: Request) =>
        request
          .clone()
          .json()
          .then((body: { email_digest: boolean }) => {
            digest = body.email_digest;
            return { email_digest: digest };
          }),
    });
    const user = userEvent.setup();
    renderApp("/account");

    // The shell settles once the page's lazily loaded code arrives; open menus after that.
    const toggle = await screen.findByRole("switch", { name: "Email me a daily digest" });
    await waitFor(() => {
      expect(toggle).toBeEnabled();
    });
    screen.getByRole("button", { name: "Notifications" }).focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByText(/Nothing yet\. Conflicts to resolve/)).toBeVisible();
    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("menu")).toBeNull();
    });
    expect(toggle).not.toBeChecked();
    await user.click(toggle);
    const [sent] = server.calls("PUT /api/v1/notifications/settings");
    expect(await sent?.json()).toEqual({ email_digest: true });
    await waitFor(() => {
      expect(toggle).toBeChecked();
    });
  });
});
