import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { USER, json, mockApi, signedOut } from "@/test/api";
import { renderApp } from "@/test/render-app";

/** Queries scoped to the account-page section with this heading. */
function section(name: string) {
  const element = screen.getByRole("heading", { name }).closest("section");
  if (!element) throw new Error(`no section titled ${name}`);
  return within(element);
}

const SESSIONS = [
  {
    id: "current",
    created_at: "2026-09-20T10:00:00Z",
    last_seen_at: new Date().toISOString(),
    ip: "127.0.0.1",
    user_agent:
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140 Safari/537.36",
    current: true,
  },
  {
    id: "phone",
    created_at: "2026-09-19T10:00:00Z",
    last_seen_at: new Date(Date.now() - 3 * 3600_000).toISOString(),
    ip: "10.0.0.9",
    user_agent:
      "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1",
    current: false,
  },
];

describe("two-factor authentication", () => {
  test("set up with the QR code, then save the recovery codes", async () => {
    let me = { ...USER };
    const codes = Array.from({ length: 10 }, (_, i) => `abcde-fgh${String(i).padStart(2, "0")}`);
    const server = mockApi({
      "GET /api/v1/auth/me": () => me,
      "GET /api/v1/auth/sessions": SESSIONS,
      "POST /api/v1/auth/2fa/setup": {
        secret: "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
        otpauth_uri: "otpauth://totp/Winnow:ada",
        qr_code: "data:image/svg+xml;base64,PHN2Zy8+",
      },
      "POST /api/v1/auth/2fa/enable": () => {
        me = { ...USER, totp_enabled: true, recovery_codes_left: 10 };
        return { recovery_codes: codes, csrf_token: "rotated" };
      },
    });
    const user = userEvent.setup();
    renderApp("/account");
    await screen.findByRole("heading", { name: "Two-factor authentication" });
    const twoFactor = section("Two-factor authentication");
    expect(twoFactor.getByText("Off")).toBeVisible();

    await user.click(twoFactor.getByRole("button", { name: "Set up two-factor authentication" }));
    expect(await twoFactor.findByAltText(/QR code/)).toHaveAttribute(
      "src",
      "data:image/svg+xml;base64,PHN2Zy8+",
    );
    expect(twoFactor.getByTestId("totp-secret")).toHaveTextContent("JBSW Y3DP EHPK 3PXP");
    await user.type(twoFactor.getByLabelText("Code from the app"), "123456");
    await user.click(twoFactor.getByRole("button", { name: "Turn on" }));

    const list = await twoFactor.findByRole("list", { name: "Recovery codes" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(10);
    expect(await server.calls("POST /api/v1/auth/2fa/enable")[0]?.json()).toEqual({
      code: "123456",
    });
    await user.click(twoFactor.getByRole("button", { name: "I have saved them" }));
    expect(await twoFactor.findByText("On")).toBeVisible();
    expect(twoFactor.getByText(/10 of 10 recovery codes left/)).toBeVisible();
  });

  test("turning it off needs the password and a code", async () => {
    let me = { ...USER, totp_enabled: true, recovery_codes_left: 2 };
    const server = mockApi({
      "GET /api/v1/auth/me": () => me,
      "GET /api/v1/auth/sessions": SESSIONS,
      "POST /api/v1/auth/2fa/disable": () => {
        me = { ...USER };
        return { csrf_token: "rotated" };
      },
    });
    const user = userEvent.setup();
    renderApp("/account");
    expect(await screen.findByText(/Make new ones before you run out/)).toBeVisible();
    const twoFactor = section("Two-factor authentication");
    await user.click(twoFactor.getByRole("button", { name: "Turn off" }));
    await user.type(twoFactor.getByLabelText("Password"), "a sturdy passphrase");
    await user.type(twoFactor.getByLabelText("Authenticator or recovery code"), "654321");
    await user.click(twoFactor.getByRole("button", { name: "Turn off two-factor" }));
    await waitFor(() => {
      expect(server.calls("POST /api/v1/auth/2fa/disable")).toHaveLength(1);
    });
    expect(await server.calls("POST /api/v1/auth/2fa/disable")[0]?.json()).toEqual({
      password: "a sturdy passphrase",
      code: "654321",
    });
    expect(
      await screen.findByRole("button", { name: "Set up two-factor authentication" }),
    ).toBeVisible();
  });
});

describe("signed-in devices", () => {
  test("lists devices and signs one out", async () => {
    const server = mockApi({
      "GET /api/v1/auth/me": USER,
      "GET /api/v1/auth/sessions": SESSIONS,
      "DELETE /api/v1/auth/sessions/phone": () => new Response(null, { status: 204 }),
    });
    const user = userEvent.setup();
    renderApp("/account");
    expect(await screen.findByText("Chrome on macOS")).toBeVisible();
    expect(screen.getByText("This device")).toBeVisible();
    expect(screen.getByText(/10\.0\.0\.9 · active 3 hours ago/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: /Sign out Safari on iOS/ }));
    await waitFor(() => {
      expect(server.calls("DELETE /api/v1/auth/sessions/phone")).toHaveLength(1);
    });
  });

  test("sign out everywhere asks first, then leaves", async () => {
    let me: object = USER;
    mockApi({
      "GET /api/v1/auth/me": () => me,
      "GET /api/v1/auth/sessions": SESSIONS,
      "POST /api/v1/auth/logout-all": () => {
        me = signedOut;
        return new Response(null, { status: 204 });
      },
    });
    const user = userEvent.setup();
    renderApp("/account");
    await user.click(await screen.findByRole("button", { name: "Sign out everywhere" }));
    expect(screen.getByText("Sign out of every device, including this one?")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Sign out everywhere" }));
    expect(await screen.findByRole("heading", { name: "Sign in to Winnow" })).toBeVisible();
  });
});

describe("shell", () => {
  test("the user menu signs out", async () => {
    mockApi({
      "GET /api/v1/auth/me": USER,
      "POST /api/v1/auth/logout": () => new Response(null, { status: 204 }),
    });
    const user = userEvent.setup();
    renderApp("/");
    // Wait for the page itself: its code is loaded lazily and the shell settles after it.
    await screen.findByRole("heading", { name: "My reviews" });
    // Keyboard users open it with Enter (guide 11.4: everything reachable by keyboard).
    screen.getByRole("button", { name: "Account menu for Ada Lovelace" }).focus();
    await user.keyboard("{Enter}");
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByText(USER.email)).toBeVisible();
    await user.click(within(menu).getByRole("menuitem", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in to Winnow" })).toBeVisible();
  });

  test("unconfirmed accounts see a banner that resends the link", async () => {
    const server = mockApi({
      "GET /api/v1/auth/me": { ...USER, email_verified: false },
      "POST /api/v1/auth/verify-email/resend": json({ status: "accepted", detail: "sent" }, 202),
    });
    const user = userEvent.setup();
    renderApp("/");
    expect(await screen.findByText(/Confirm your email address to join reviews/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Send a new link" }));
    expect(await screen.findByText(`We sent a new link to ${USER.email}.`)).toBeVisible();
    expect(server.calls("POST /api/v1/auth/verify-email/resend")).toHaveLength(1);
  });

  test("a session that ends while the page is open leads back to sign in", async () => {
    mockApi({ "GET /api/v1/auth/me": USER, "GET /api/v1/auth/sessions": signedOut });
    const { router } = renderApp("/account");
    expect(await screen.findByRole("heading", { name: "Sign in to Winnow" })).toBeVisible();
    expect(router.state.location.search).toEqual({ redirect: "/account" });
  });
});
