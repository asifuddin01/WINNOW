import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { USER, mockApi } from "@/test/api";
import { renderApp } from "@/test/render-app";

const ADMIN = { ...USER, is_instance_admin: true };
const GRACE = "00000000-0000-4000-8000-0000000000g2".replace("g", "a");

function person(extra: Record<string, unknown> = {}) {
  return {
    id: USER.id,
    name: USER.name,
    email: USER.email,
    email_verified: true,
    two_factor: false,
    is_instance_admin: true,
    disabled: false,
    reviews: 3,
    created_at: "2026-09-20T10:00:00Z",
    ...extra,
  };
}

const PEOPLE = {
  items: [
    person({
      id: GRACE,
      name: "Grace Hopper",
      email: "grace@example.org",
      is_instance_admin: false,
      two_factor: true,
      email_verified: false,
      reviews: 1,
    }),
    person(),
  ],
  next_cursor: null,
  total: 2,
};

const SETTINGS = {
  registration: { value: "open", source: "environment" },
  unpaywall_email: { value: null, source: "environment" },
  public_url: "https://winnow.example.org",
  single_user: false,
  email_configured: true,
  email_from: "Winnow <no-reply@example.org>",
  storage_backend: "local",
  open_access_lookup: true,
  llm_provider: "anthropic",
  llm_model: "claude-sonnet-5",
  llm_configured: true,
  virus_scanner: false,
  max_upload_mb: 200,
  max_pdf_mb: 100,
  max_backup_mb: 2048,
  version: "0.9.0",
};

describe("instance admin", () => {
  test("someone who is not an administrator finds nothing, and no link to it", async () => {
    mockApi({ "GET /api/v1/auth/me": USER });
    renderApp("/admin");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Instance admin" })).toBeNull();
  });

  test("people are listed and searched; an account is disabled after confirming", async () => {
    const server = mockApi({
      "GET /api/v1/auth/me": ADMIN,
      "GET /api/v1/admin/users": (request: Request) =>
        new URL(request.url).searchParams.get("q") === "grace"
          ? { ...PEOPLE, items: [PEOPLE.items[0]], total: 1 }
          : PEOPLE,
      [`POST /api/v1/admin/users/${GRACE}/disable`]: () => new Response(null, { status: 200 }),
      [`POST /api/v1/admin/users/${GRACE}/reset-2fa`]: () => new Response(null, { status: 200 }),
    });
    const user = userEvent.setup();
    renderApp("/admin");

    const table = await screen.findByRole("table", { name: "Accounts on this Winnow" });
    expect(screen.getByRole("link", { name: "Instance admin" })).toBeVisible();
    const grace = within(table).getByRole("row", { name: /Grace Hopper/ });
    expect(grace).toHaveTextContent("Two-factor on");
    expect(grace).toHaveTextContent("Email not confirmed");
    const me = within(table).getByRole("row", { name: /\(you\)/ });
    expect(within(me).queryByRole("button", { name: /Actions for/ })).toBeNull(); // nothing to do to yourself

    await user.type(screen.getByLabelText("Find someone"), "grace");
    expect(await screen.findByText("1 account")).toBeVisible();
    // The search draws a new table.
    const found = screen.getByRole("table", { name: "Accounts on this Winnow" });

    within(found).getByRole("button", { name: "Actions for Grace Hopper" }).focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("menuitem", { name: "Disable" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Disable this account?" });
    expect(dialog).toHaveTextContent("Their reviews and work are untouched");
    await user.click(within(dialog).getByRole("button", { name: "Disable" }));
    await waitFor(() => {
      expect(server.calls(`POST /api/v1/admin/users/${GRACE}/disable`)).toHaveLength(1);
    });

    within(found).getByRole("button", { name: "Actions for Grace Hopper" }).focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("menuitem", { name: "Reset two-factor" }));
    const reset = await screen.findByRole("alertdialog", { name: /Reset two-factor/ });
    await user.click(within(reset).getByRole("button", { name: "Cancel" }));
    expect(server.calls(`POST /api/v1/admin/users/${GRACE}/reset-2fa`)).toHaveLength(0);
  });

  test("registration and the Unpaywall email change here; the rest is shown, never secrets", async () => {
    let current = SETTINGS;
    const server = mockApi({
      "GET /api/v1/auth/me": ADMIN,
      "GET /api/v1/admin/settings": () => current,
      "PATCH /api/v1/admin/settings": () => {
        current = { ...SETTINGS, registration: { value: "closed", source: "admin" } };
        return current;
      },
    });
    const user = userEvent.setup();
    renderApp("/admin/settings");

    expect(await screen.findByText("claude-sonnet-5", { exact: false })).toBeVisible();
    expect(screen.getByText("Not set up: PDFs are marked unscanned")).toBeVisible();
    screen.getByLabelText("Who can create an account").focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("option", { name: /^Closed/ }));
    const [first] = server.calls("PATCH /api/v1/admin/settings");
    expect(await first?.json()).toEqual({ registration: "closed" });

    await user.click(await screen.findByRole("button", { name: "Use the value in .env instead" }));
    await user.type(screen.getByLabelText("Email for Unpaywall"), "lib@example.org");
    await user.click(screen.getByRole("button", { name: "Save email" }));
    const calls = server.calls("PATCH /api/v1/admin/settings");
    expect(await calls[1]?.json()).toEqual({ registration: "environment" });
    expect(await calls[2]?.json()).toEqual({ unpaywall_email: "lib@example.org" });
  });

  test("health: worker, queue, backup, disk and database", async () => {
    mockApi({
      "GET /api/v1/auth/me": ADMIN,
      "GET /api/v1/admin/health": {
        database_bytes: 50 * 1024 ** 2,
        queue: {
          waiting: 3,
          worker_alive: true,
          worker_report: { j_complete: 12, j_failed: 1, j_ongoing: 2 },
        },
        disk: { path: "/data", total_bytes: 100, used_bytes: 95, free_bytes: 5 },
        last_backup: { at: new Date().toISOString(), file: "winnow.tar.age", size_bytes: 2048 },
        users: 4,
        reviews: 2,
        records: 1500,
        version: "0.9.0",
      },
    });
    renderApp("/admin/health");
    const worker = await screen.findByRole("region", { name: "Worker" });
    expect(worker).toHaveTextContent("Running");
    expect(worker).toHaveTextContent("12 jobs done, 1 failed, 2 running");
    expect(screen.getByRole("region", { name: "Queue" })).toHaveTextContent("3 waiting");
    expect(screen.getByRole("region", { name: "Last backup" })).toHaveTextContent(
      "winnow.tar.age · 2.0 KB",
    );
    expect(screen.getByRole("progressbar", { name: "Disk used" })).toHaveAttribute(
      "aria-valuenow",
      "95",
    );
    expect(screen.getByRole("region", { name: "Database" })).toHaveTextContent(
      "4 people, 2 reviews, 1,500 records",
    );
  });

  test("health says what is wrong: no worker, no backup, files in a bucket", async () => {
    mockApi({
      "GET /api/v1/auth/me": ADMIN,
      "GET /api/v1/admin/health": {
        database_bytes: 1024,
        queue: { waiting: 0, worker_alive: false, worker_report: {} },
        disk: null,
        last_backup: null,
        users: 1,
        reviews: 0,
        records: 0,
        version: "0.9.0",
      },
    });
    renderApp("/admin/health");
    expect(await screen.findByText("Not responding")).toBeVisible();
    expect(screen.getByText("None recorded")).toBeVisible();
    expect(screen.getByText("Files are kept in an S3 bucket.")).toBeVisible();
  });
});
