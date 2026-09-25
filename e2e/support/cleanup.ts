import { execSync } from "node:child_process";

/**
 * Remove what end-to-end runs leave in the local stack: the reviews of their throwaway
 * accounts (e2e-…@example.com; records, PDFs and batches go with them) and the stored
 * files nothing refers to any more. Files younger than a minute are left for the next
 * run, so an upload being made on the same instance is never caught half-way. CI's stack
 * is discarded after each run, so it does nothing there.
 */
export function removeTestData(): void {
  if (process.env.CI) return;
  const run = (command: string) => execSync(command, { stdio: "ignore", cwd: ".." });
  run(
    `docker compose exec -T db psql -U winnow -d winnow -c "delete from projects where owner_id in (select id from users where email like 'e2e-%@example.com')"`,
  );
  // The admin journey promotes (and may disable) a fixture account: none stays that way.
  run(
    `docker compose exec -T db psql -U winnow -d winnow -c "update users set is_instance_admin = false, disabled_at = null where email like 'e2e-%@example.com'"`,
  );
  run(`docker compose exec -T api python -m app.cli sweep-files --apply --older-than-minutes 1`);
}
