import { execSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";

import { request, type FullConfig } from "@playwright/test";

import { createSignedInUser } from "./support/api";
import { uniqueEmail } from "./support/mail";

export const SIGNED_IN_STATE = ".auth/signed-in.json";

/**
 * Runs once before the suite, against the running `make up` stack:
 * - clears the Redis rate-limit counters, so reruns within an hour are not refused;
 * - creates one verified, signed-in account whose cookies most tests reuse.
 */
export default async function globalSetup(config: FullConfig): Promise<void> {
  execSync(
    `docker compose exec -T redis sh -c "redis-cli --scan --pattern 'rl:*' | xargs -r redis-cli del"`,
    { stdio: "ignore", cwd: ".." },
  );
  const baseURL = config.projects[0]?.use.baseURL ?? "http://localhost:8080";
  const context = await request.newContext({ baseURL });
  await createSignedInUser(context, baseURL, uniqueEmail("shared"));
  mkdirSync(dirname(SIGNED_IN_STATE), { recursive: true });
  await context.storageState({ path: SIGNED_IN_STATE });
  await context.dispose();
}
