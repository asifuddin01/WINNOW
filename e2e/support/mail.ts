import { expect, type APIRequestContext } from "@playwright/test";

export const MAILPIT = process.env.MAILPIT_URL ?? "http://localhost:8025";

const SUBJECTS = {
  verify: "Confirm your email",
  reset: "Reset your Winnow password",
  invite: "You are invited to a review",
};

interface MailSummary {
  ID: string;
  Subject: string;
}

/**
 * The path of the newest `/{page}/{token}` link emailed to `to` (via Mailpit, which
 * catches all mail in the development stack). Waits for the worker to deliver it.
 */
export async function emailedLink(
  request: APIRequestContext,
  to: string,
  page: "verify" | "reset" | "invite",
): Promise<string> {
  const query = encodeURIComponent(`to:"${to}"`);
  let newest: MailSummary | undefined;
  await expect
    .poll(
      async () => {
        const response = await request.get(`${MAILPIT}/api/v1/search?query=${query}`);
        const body = (await response.json()) as { messages: MailSummary[] | null };
        newest = body.messages?.find((m) => m.Subject.startsWith(SUBJECTS[page]));
        return newest?.ID;
      },
      { timeout: 20_000, message: `no ${page} email for ${to}` },
    )
    .toBeTruthy();
  const message = (await (
    await request.get(`${MAILPIT}/api/v1/message/${newest?.ID ?? ""}`)
  ).json()) as {
    Text: string;
  };
  const link = new RegExp(`https?://\\S+?(/${page}/[A-Za-z0-9_-]+)`).exec(message.Text);
  if (!link?.[1]) throw new Error(`no ${page} link in the email to ${to}`);
  return link[1];
}

export function uniqueEmail(label: string): string {
  return `e2e-${label}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}@example.com`;
}
