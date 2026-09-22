import { expect, test, type Page } from "@playwright/test";
import * as OTPAuth from "otpauth";

import { PASSWORD, clearRegistrationLimits } from "../support/api";
import { emailedLink, uniqueEmail } from "../support/mail";

const NEW_PASSWORD = "a replacement passphrase";

async function signIn(page: Page, email: string, password: string) {
  await expect(page.getByRole("heading", { name: "Sign in to Winnow" })).toBeVisible();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

async function openUserMenu(page: Page) {
  await page.getByRole("button", { name: /^Account menu for / }).click();
}

/**
 * Acceptance for Phase 1: the whole account life cycle in a real browser, with a real
 * authenticator algorithm (otpauth computes codes exactly as an authenticator app does).
 */
test("register, verify, 2FA, sign out and in, reset the password", async ({ page, request }) => {
  test.setTimeout(120_000); // two emails through the worker, two sign-ins with 2FA, a reset
  clearRegistrationLimits();
  const email = uniqueEmail("journey");

  // Register and confirm the email address from the link Mailpit caught.
  await page.goto("/register");
  await page.getByLabel("Name", { exact: true }).fill("Grace Hopper");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();

  await page.goto(await emailedLink(request, email, "verify"));
  await page.getByRole("button", { name: "Confirm email address" }).click();
  await expect(page.getByRole("heading", { name: "Email confirmed" })).toBeVisible();
  await page.getByRole("link", { name: "Sign in" }).click();

  // Sign in; a new session id arrives.
  await signIn(page, email, PASSWORD);
  await expect(page.getByRole("heading", { name: "My reviews" })).toBeVisible();
  const cookies = await page.context().cookies();
  const session = cookies.find((c) => c.name === "__Host-winnow_session");
  expect(session?.httpOnly).toBe(true);
  expect(session?.secure).toBe(true);
  expect(session?.sameSite).toBe("Lax");

  // Turn on two-factor authentication.
  await openUserMenu(page);
  await page.getByRole("menuitem", { name: "Account and security" }).click();
  await expect(page.getByRole("heading", { name: "Account and security" })).toBeVisible();
  await page.getByRole("button", { name: "Set up two-factor authentication" }).click();
  await expect(page.getByAltText(/QR code/)).toBeVisible();
  const secret = (await page.getByTestId("totp-secret").innerText()).replace(/\s/g, "");
  const totp = new OTPAuth.TOTP({
    secret: OTPAuth.Secret.fromBase32(secret),
    digits: 6,
    period: 30,
  });
  await page.getByLabel("Code from the app", { exact: true }).fill(totp.generate());
  await page.getByRole("button", { name: "Turn on" }).click();
  const codeItems = page.getByRole("list", { name: "Recovery codes" }).getByRole("listitem");
  await expect(codeItems).toHaveCount(10);
  const codes = await codeItems.allInnerTexts();
  await page.getByRole("button", { name: "I have saved them" }).click();
  await expect(page.getByText("10 of 10 recovery codes left.")).toBeVisible();

  // Sign out, then back in: now the code is asked for. The enabling code already used
  // this 30-second window, so use the next one (accepted for clock drift).
  await openUserMenu(page);
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in to Winnow" })).toBeVisible();
  await signIn(page, email, PASSWORD);
  await expect(page.getByRole("heading", { name: "Two-step verification" })).toBeVisible();
  await page
    .getByLabel("Authentication code")
    .fill(totp.generate({ timestamp: Date.now() + 30_000 }));
  await page.getByRole("button", { name: "Verify and sign in" }).click();
  await expect(page.getByRole("heading", { name: "My reviews" })).toBeVisible();
  await openUserMenu(page);
  await page.getByRole("menuitem", { name: "Sign out" }).click();

  // Forgot the password: reset it from the emailed link.
  await page.getByRole("link", { name: "Forgot your password?" }).click();
  await expect(page.getByRole("heading", { name: "Reset your password" })).toBeVisible();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByRole("status")).toContainText("If an account uses that address");
  await page.goto(await emailedLink(request, email, "reset"));
  await page.getByLabel("New password", { exact: true }).fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "Set new password" }).click();
  await expect(page.getByRole("heading", { name: "Password changed" })).toBeVisible();

  // The old password no longer works; the new one plus a recovery code does.
  await page.getByRole("link", { name: "Sign in" }).click();
  await signIn(page, email, PASSWORD);
  await expect(page.getByRole("alert")).toContainText("Email or password is incorrect.");
  await signIn(page, email, NEW_PASSWORD);
  await page.getByLabel("Authentication code", { exact: true }).fill(codes[0] ?? "");
  await page.getByRole("button", { name: "Verify and sign in" }).click();
  await expect(page.getByRole("heading", { name: "My reviews" })).toBeVisible();
  await page.goto("/account");
  await expect(page.getByText("9 of 10 recovery codes left.")).toBeVisible();
  await expect(page.getByText("This device")).toBeVisible();
});

test("a wrong password is refused without saying whether the account exists", async ({ page }) => {
  await page.goto("/login");
  await signIn(page, uniqueEmail("nobody"), "definitely not it");
  await expect(page.getByRole("alert")).toContainText("Email or password is incorrect.");
  await expect(page).toHaveURL(/\/login/);
});
