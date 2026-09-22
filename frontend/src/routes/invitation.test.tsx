import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { PROJECT, USER, mockApi, problemResponse, projectRoutes } from "@/test/api";
import { renderApp } from "@/test/render-app";

const TOKEN = "an-invitation-token-000";
const PREVIEW = {
  project_title: "Shift work and sleep quality",
  inviter_name: "Ada Lovelace",
  role: "reviewer",
  email_hint: "g•••@example.org",
  expires_at: "2026-09-29T10:00:00Z",
  state: "pending",
};

describe("the invitation page", () => {
  test("signed out, it offers to sign in or register", async () => {
    mockApi({ [`GET /api/v1/invites/${TOKEN}`]: PREVIEW });
    renderApp(`/invite/${TOKEN}`);

    expect(await screen.findByRole("heading", { name: "You are invited" })).toBeVisible();
    expect(screen.getByText(/Shift work and sleep quality/)).toBeVisible();
    expect(screen.getByText("g•••@example.org")).toBeVisible();
    expect(screen.getByRole("link", { name: "Sign in to accept" })).toHaveAttribute(
      "href",
      `/login?redirect=%2Finvite%2F${TOKEN}`,
    );
    expect(screen.getByRole("link", { name: "Create an account" })).toHaveAttribute(
      "href",
      `/register?invite=${TOKEN}`,
    );
  });

  test("signed in, accepting opens the review", async () => {
    const server = mockApi({
      "GET /api/v1/auth/me": USER,
      ...projectRoutes(),
      [`GET /api/v1/invites/${TOKEN}`]: PREVIEW,
      [`POST /api/v1/invites/${TOKEN}/accept`]: { project_id: PROJECT.id },
    });
    const user = userEvent.setup();
    renderApp(`/invite/${TOKEN}`);

    await user.click(await screen.findByRole("button", { name: "Accept invitation" }));
    expect(server.calls(`POST /api/v1/invites/${TOKEN}/accept`)).toHaveLength(1);
    expect(await screen.findByRole("heading", { level: 1, name: PROJECT.title })).toBeVisible();
  });

  test("an invitation for another address says so", async () => {
    mockApi({
      "GET /api/v1/auth/me": USER,
      [`GET /api/v1/invites/${TOKEN}`]: PREVIEW,
      [`POST /api/v1/invites/${TOKEN}/accept`]: () =>
        problemResponse(403, {
          title: "Forbidden",
          code: "invite_email_mismatch",
          detail:
            "This invitation is for g•••@example.org. Sign in with that address to accept it.",
        }),
    });
    const user = userEvent.setup();
    renderApp(`/invite/${TOKEN}`);

    await user.click(await screen.findByRole("button", { name: "Accept invitation" }));
    // The page itself says so; the toast repeats it.
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/Sign in with that address/);
  });

  test("a withdrawn link explains itself", async () => {
    mockApi({
      [`GET /api/v1/invites/${TOKEN}`]: () =>
        problemResponse(400, {
          title: "Bad Request",
          code: "invalid_token",
          detail: "This invitation link is not valid. It may have been withdrawn.",
        }),
    });
    renderApp(`/invite/${TOKEN}`);

    expect(
      await screen.findByRole("heading", { name: "This invitation does not work" }),
    ).toBeVisible();
    expect(screen.getByText(/may have been withdrawn/)).toBeVisible();
  });

  test("an expired one asks for a new invitation", async () => {
    mockApi({ [`GET /api/v1/invites/${TOKEN}`]: { ...PREVIEW, state: "expired" } });
    renderApp(`/invite/${TOKEN}`);

    expect(
      await screen.findByRole("heading", { name: "This invitation has expired" }),
    ).toBeVisible();
    expect(screen.getByText("Invitations last a week. Ask for a new one.")).toBeVisible();
  });
});
