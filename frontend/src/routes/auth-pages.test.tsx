import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { OPTIONS, USER, json, mockApi, problemResponse, signedOut } from "@/test/api";
import { renderApp } from "@/test/render-app";

const PASSWORD = "a sturdy passphrase";

function expectFooter() {
  expect(
    within(screen.getByRole("contentinfo")).getByRole("link", { name: "Asif" }),
  ).toHaveAttribute("href", "https://asifuddin.com");
}

describe("sign in", () => {
  test("signed-out visitors are sent to sign in and brought back afterwards", async () => {
    let me: object = signedOut;
    const server = mockApi({
      "GET /api/v1/auth/me": () => me,
      "POST /api/v1/auth/login": () => {
        me = USER;
        return { user: USER, csrf_token: "session-token" };
      },
    });
    const user = userEvent.setup();
    const { router } = renderApp("/account");
    expect(await screen.findByRole("heading", { name: "Sign in to Winnow" })).toBeVisible();
    expect(router.state.location.search).toEqual({ redirect: "/account" });
    expectFooter();

    await user.type(screen.getByLabelText("Email"), USER.email);
    await user.type(screen.getByLabelText("Password"), PASSWORD);
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Account and security" })).toBeVisible();
    const login = server.calls("POST /api/v1/auth/login")[0];
    expect(await login?.json()).toEqual({ email: USER.email, password: PASSWORD });
  });

  test("checks the form before calling the server", async () => {
    const server = mockApi();
    const user = userEvent.setup();
    renderApp("/login");
    await user.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(screen.getByText("Enter a valid email address.")).toBeVisible();
    expect(screen.getByText("Enter your password.")).toBeVisible();
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
    expect(server.calls("POST /api/v1/auth/login")).toHaveLength(0);
  });

  test("shows the server's reason when sign-in fails", async () => {
    mockApi({
      "POST /api/v1/auth/login": problemResponse(401, {
        title: "Unauthorized",
        code: "invalid_credentials",
        detail: "Email or password is incorrect.",
      }),
    });
    const user = userEvent.setup();
    renderApp("/login");
    await user.type(await screen.findByLabelText("Email"), USER.email);
    await user.type(screen.getByLabelText("Password"), "wrong password!");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is incorrect.");
  });

  test("asks for the authenticator code when two-factor is on", async () => {
    let me: object = signedOut;
    const server = mockApi({
      "GET /api/v1/auth/me": () => me,
      "POST /api/v1/auth/login": async (request) => {
        const body = (await request.json()) as { totp?: string };
        if (!body.totp)
          return problemResponse(401, {
            title: "Unauthorized",
            code: "totp_required",
            detail: "Enter the code.",
          });
        if (body.totp !== "123456")
          return problemResponse(401, {
            title: "Unauthorized",
            code: "invalid_totp",
            detail: "That code is not valid.",
          });
        me = USER;
        return { user: USER, csrf_token: "t" };
      },
    });
    const user = userEvent.setup();
    renderApp("/login");
    await user.type(await screen.findByLabelText("Email"), USER.email);
    await user.type(screen.getByLabelText("Password"), PASSWORD);
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    const code = await screen.findByLabelText("Authentication code");
    expect(screen.getByRole("heading", { name: "Two-step verification" })).toBeVisible();
    expect(code).toHaveFocus();
    await user.type(code, "000000");
    await user.click(screen.getByRole("button", { name: "Verify and sign in" }));
    expect(await screen.findByText("That code is not valid.")).toBeVisible();
    await user.clear(code);
    await user.type(code, "123456");
    await user.click(screen.getByRole("button", { name: "Verify and sign in" }));
    expect(await screen.findByRole("heading", { name: "My reviews" })).toBeVisible();
    expect(server.calls("POST /api/v1/auth/login")).toHaveLength(3);
  });

  test("signed-in visitors skip the sign-in page", async () => {
    mockApi({ "GET /api/v1/auth/me": USER });
    renderApp("/login");
    expect(await screen.findByRole("heading", { name: "My reviews" })).toBeVisible();
  });
});

describe("register", () => {
  test("sends a confirmation link", async () => {
    const server = mockApi({
      "POST /api/v1/auth/register": json({ status: "accepted", detail: "ok" }, 202),
    });
    const user = userEvent.setup();
    renderApp("/register");
    await user.type(await screen.findByLabelText("Name"), "Ada Lovelace");
    await user.type(screen.getByLabelText("Email"), USER.email);
    await user.type(screen.getByLabelText("Password"), PASSWORD);
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("heading", { name: "Check your email" })).toBeVisible();
    expect(screen.getByText(USER.email)).toBeVisible();
    expect(await server.calls("POST /api/v1/auth/register")[0]?.json()).toEqual({
      name: "Ada Lovelace",
      email: USER.email,
      password: PASSWORD,
    });
    expectFooter();
  });

  test("asks for 12 characters and shows the server's password verdict", async () => {
    mockApi({
      "POST /api/v1/auth/register": problemResponse(422, {
        title: "Unprocessable",
        code: "weak_password",
        detail: "This password has appeared in a known data breach.",
      }),
    });
    const user = userEvent.setup();
    renderApp("/register");
    await user.type(await screen.findByLabelText("Name"), "Ada");
    await user.type(screen.getByLabelText("Email"), USER.email);
    await user.type(screen.getByLabelText("Password"), "short");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Use at least 12 characters.")).toBeVisible();
    await user.clear(screen.getByLabelText("Password"));
    await user.type(screen.getByLabelText("Password"), "password12345");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText(/known data breach/)).toBeVisible();
  });

  test("explains closed registration", async () => {
    mockApi({ "GET /api/v1/auth/options": { ...OPTIONS, registration: "invite_only" } });
    renderApp("/register");
    expect(await screen.findByRole("heading", { name: "Registration is closed" })).toBeVisible();
    expect(screen.getByText(/by invitation/)).toBeVisible();
  });
});

describe("email links", () => {
  test("confirming an email takes a click", async () => {
    const server = mockApi({ "POST /api/v1/auth/verify-email": USER });
    const user = userEvent.setup();
    renderApp("/verify/abcdefghijklmnopqrstuvwxyz");
    await user.click(await screen.findByRole("button", { name: "Confirm email address" }));
    expect(await screen.findByRole("heading", { name: "Email confirmed" })).toBeVisible();
    expect(await server.calls("POST /api/v1/auth/verify-email")[0]?.json()).toEqual({
      token: "abcdefghijklmnopqrstuvwxyz",
    });
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  });

  test("a spent link says so", async () => {
    mockApi({
      "POST /api/v1/auth/verify-email": problemResponse(400, {
        title: "Bad Request",
        code: "invalid_token",
        detail: "This link is invalid or has expired. Request a new one.",
      }),
    });
    const user = userEvent.setup();
    renderApp("/verify/abcdefghijklmnopqrstuvwxyz");
    await user.click(await screen.findByRole("button", { name: "Confirm email address" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
  });

  test("forgot password gives the same answer for every address", async () => {
    mockApi({
      "POST /api/v1/auth/password/forgot": json({ status: "accepted", detail: "ok" }, 202),
    });
    const user = userEvent.setup();
    renderApp("/forgot");
    await user.type(await screen.findByLabelText("Email"), "someone@example.org");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByRole("status")).toHaveTextContent("If an account uses that address");
  });

  test("resetting the password", async () => {
    const server = mockApi({
      "POST /api/v1/auth/password/reset": () => new Response(null, { status: 204 }),
    });
    const user = userEvent.setup();
    renderApp("/reset/abcdefghijklmnopqrstuvwxyz");
    await user.type(await screen.findByLabelText("New password"), PASSWORD);
    await user.click(screen.getByRole("button", { name: "Set new password" }));
    expect(await screen.findByRole("heading", { name: "Password changed" })).toBeVisible();
    expect(await server.calls("POST /api/v1/auth/password/reset")[0]?.json()).toEqual({
      token: "abcdefghijklmnopqrstuvwxyz",
      password: PASSWORD,
    });
  });

  test("an expired reset link offers a new one", async () => {
    mockApi({
      "POST /api/v1/auth/password/reset": problemResponse(400, {
        title: "Bad Request",
        code: "invalid_token",
        detail: "This link is invalid or has expired. Request a new one.",
      }),
    });
    const user = userEvent.setup();
    renderApp("/reset/abcdefghijklmnopqrstuvwxyz");
    await user.type(await screen.findByLabelText("New password"), PASSWORD);
    await user.click(screen.getByRole("button", { name: "Set new password" }));
    expect(await screen.findByRole("link", { name: "Send a new link" })).toHaveAttribute(
      "href",
      "/forgot",
    );
  });
});

describe("single-user mode", () => {
  test("the first run creates the administrator", async () => {
    let options: object = { ...OPTIONS, single_user: true, needs_setup: true };
    let me: object = signedOut;
    mockApi({
      "GET /api/v1/auth/options": () => options,
      "GET /api/v1/auth/me": () => me,
      "POST /api/v1/auth/setup": () => {
        options = { ...OPTIONS, single_user: true };
        me = { ...USER, is_instance_admin: true };
        return json({ user: me, csrf_token: "t" }, 201);
      },
    });
    const user = userEvent.setup();
    renderApp("/login");
    expect(await screen.findByRole("heading", { name: "Set up Winnow" })).toBeVisible();
    await user.type(screen.getByLabelText("Name"), "Ada Lovelace");
    await user.type(screen.getByLabelText("Email"), USER.email);
    await user.type(screen.getByLabelText("Password"), PASSWORD);
    await user.click(screen.getByRole("button", { name: "Create account and start" }));
    expect(await screen.findByRole("heading", { name: "My reviews" })).toBeVisible();
  });
});

describe("sign in with Google", () => {
  const GOOGLE_ON = { ...OPTIONS, google_enabled: true };

  test("offers Google when the instance has it, keeping the destination", async () => {
    mockApi({ "GET /api/v1/auth/options": GOOGLE_ON });
    renderApp("/login?redirect=%2Faccount");
    const google = await screen.findByRole("link", { name: "Continue with Google" });
    expect(google).toHaveAttribute("href", "/api/v1/auth/google/start?redirect=%2Faccount");
  });

  test("hides Google when it is not configured", async () => {
    renderApp("/login");
    await screen.findByRole("heading", { name: "Sign in to Winnow" });
    expect(screen.queryByRole("link", { name: "Continue with Google" })).not.toBeInTheDocument();
  });

  test("explains what went wrong at Google", async () => {
    mockApi({ "GET /api/v1/auth/options": GOOGLE_ON });
    renderApp("/login?error=google_unverified");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Google has not verified that email",
    );
  });

  test("an unknown error code still gets a sentence", async () => {
    renderApp("/login?error=something_new");
    expect(await screen.findByRole("alert")).toHaveTextContent("Google sign-in did not finish");
  });

  test("a two-factor account finishes with its code", async () => {
    let me: object = signedOut;
    const server = mockApi({
      "GET /api/v1/auth/options": GOOGLE_ON,
      "GET /api/v1/auth/me": () => me,
      "POST /api/v1/auth/google/two-factor": () => {
        me = USER;
        return { user: USER, csrf_token: "t", redirect: "/account" };
      },
    });
    const user = userEvent.setup();
    renderApp("/login?step=google-2fa");
    expect(await screen.findByText(/Google confirmed who you are/)).toBeVisible();
    await user.type(screen.getByLabelText("Authentication code"), "123456");
    await user.click(screen.getByRole("button", { name: "Verify and sign in" }));
    expect(await screen.findByRole("heading", { name: "Account and security" })).toBeVisible();
    expect(await server.calls("POST /api/v1/auth/google/two-factor")[0]?.json()).toEqual({
      code: "123456",
    });
  });

  test("an expired Google sign-in says to start again", async () => {
    mockApi({
      "POST /api/v1/auth/google/two-factor": problemResponse(401, {
        title: "Unauthorized",
        code: "google_pending_expired",
        detail: "This Google sign-in has expired. Start again.",
      }),
    });
    const user = userEvent.setup();
    renderApp("/login?step=google-2fa");
    await user.type(await screen.findByLabelText("Authentication code"), "123456");
    await user.click(screen.getByRole("button", { name: "Verify and sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("has expired");
    expect(screen.getByRole("link", { name: "Sign in again" })).toHaveAttribute("href", "/login");
  });

  test("registration offers Google too", async () => {
    mockApi({ "GET /api/v1/auth/options": GOOGLE_ON });
    renderApp("/register");
    expect(await screen.findByRole("link", { name: "Sign up with Google" })).toHaveAttribute(
      "href",
      "/api/v1/auth/google/start",
    );
  });
});
