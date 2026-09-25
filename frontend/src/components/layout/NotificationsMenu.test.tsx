import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import type { Notice } from "@/api/notifications";
import { describeNotice } from "@/features/notifications/wording";
import { PROJECT, USER, mockApi, projectRoutes } from "@/test/api";
import { renderApp } from "@/test/render-app";

const RID = "00000000-0000-4000-8000-000000000001";

function notice(extra: Partial<Notice>): Notice {
  return {
    id: "n1",
    kind: "conflicts",
    project_id: PROJECT.id,
    count: 1,
    data: { project_title: PROJECT.title },
    read: false,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...extra,
  };
}

const NOTICES = [
  notice({ id: "n1", kind: "conflicts", count: 3 }),
  notice({
    id: "n2",
    kind: "mention",
    data: {
      project_title: PROJECT.title,
      by: "Grace Hopper",
      excerpt: "@Ada check this",
      record_id: RID,
    },
  }),
  notice({
    id: "n3",
    kind: "invite",
    project_id: null,
    read: true,
    data: { project_title: "Caffeine", by: "Hedy" },
  }),
];

function nth(index: number): Notice {
  const found = NOTICES[index];
  if (!found) throw new Error(`no notice ${index}`);
  return found;
}

function routes(extra: Record<string, unknown> = {}) {
  return {
    "GET /api/v1/auth/me": USER,
    ...projectRoutes(),
    "GET /api/v1/notifications/unread": { unread: 2 },
    "GET /api/v1/notifications": { items: NOTICES, next_cursor: null, unread: 2 },
    "POST /api/v1/notifications/n1/read": () => new Response(null, { status: 204 }),
    "POST /api/v1/notifications/read-all": () => new Response(null, { status: 204 }),
    ...extra,
  };
}

describe("notifications", () => {
  test("the bell counts what is unread; a notice opens where it points and is marked read", async () => {
    const server = mockApi(routes());
    const user = userEvent.setup();
    const { router } = renderApp("/");
    await screen.findByRole("heading", { name: "My reviews" });

    const bell = await screen.findByRole("button", { name: "Notifications, 2 unread" });
    await user.click(bell);
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByText(/3 new conflicts to resolve in/)).toBeVisible();
    expect(within(menu).getByText(/Grace Hopper mentioned you/)).toBeVisible();
    expect(within(menu).getByText(/Hedy invited you to Caffeine/)).toBeVisible();
    expect(within(menu).getAllByText("(unread)")).toHaveLength(2);

    await user.click(within(menu).getByText(/3 new conflicts/));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/p/${PROJECT.id}/conflicts`);
    });
    expect(server.calls("POST /api/v1/notifications/n1/read")).toHaveLength(1);
    // Let the menu finish closing, or Radix's shared layer state outlives the test.
    await waitFor(() => {
      expect(screen.queryByRole("menu")).toBeNull();
    });
  });

  test("everything can be marked read at once", async () => {
    const server = mockApi(routes());
    const user = userEvent.setup();
    renderApp("/");
    // The shell settles once the page's lazily loaded code arrives; open menus after that.
    await screen.findByRole("heading", { name: "My reviews" });
    (await screen.findByRole("button", { name: /Notifications, 2 unread/ })).focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("menuitem", { name: "Mark all as read" }));
    expect(server.calls("POST /api/v1/notifications/read-all")).toHaveLength(1);
  });

  test("nothing yet says what will appear", async () => {
    mockApi(
      routes({
        "GET /api/v1/notifications/unread": { unread: 0 },
        "GET /api/v1/notifications": { items: [], next_cursor: null, unread: 0 },
      }),
    );
    const user = userEvent.setup();
    renderApp("/");
    await screen.findByRole("heading", { name: "My reviews" });
    screen.getByRole("button", { name: "Notifications" }).focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByText(/Nothing yet\. Conflicts to resolve/)).toBeVisible();
  });

  test("every kind in words, with where it leads", () => {
    const pid = PROJECT.id;
    expect(describeNotice(notice({ count: 1 }))).toEqual({
      text: `1 new conflict to resolve in ${PROJECT.title}`,
      to: `/p/${pid}/conflicts`,
    });
    expect(describeNotice(nth(1)).to).toBe(`/p/${pid}/records?record=${RID}`);
    expect(describeNotice(nth(2)).to).toBeNull();
    expect(
      describeNotice(
        notice({
          kind: "import_finished",
          data: { project_title: "R", filename: "pubmed.nbib", imported: 1204 },
        }),
      ),
    ).toEqual({
      text: "Your import of pubmed.nbib into R finished: 1,204 records",
      to: `/p/${pid}/import`,
    });
    expect(describeNotice(notice({ kind: "import_failed", data: {} })).text).toBe(
      "Your import of a file into a review failed",
    );
    expect(describeNotice(notice({ kind: "conflicts", project_id: null })).to).toBeNull();
  });

  test("the daily digest is switched on in account settings", async () => {
    const server = mockApi(
      routes({
        "GET /api/v1/auth/sessions": [],
        "GET /api/v1/notifications/settings": { email_digest: false },
        "PUT /api/v1/notifications/settings": { email_digest: true },
      }),
    );
    const user = userEvent.setup();
    renderApp("/account");
    const digest = await screen.findByRole("switch", { name: "Email me a daily digest" });
    await waitFor(() => {
      expect(digest).toBeEnabled();
    });
    expect(digest).not.toBeChecked();
    await user.click(digest);
    const [sent] = server.calls("PUT /api/v1/notifications/settings");
    expect(await sent?.json()).toEqual({ email_digest: true });
  });
});
