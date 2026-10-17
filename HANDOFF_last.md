# Winnow: handoff

Written 2026-10-18. It records where the build stands, so any session (Claude Code, Codex or
a person) can pick up from this exact point.

- **Repository:** `~/Web/WINNOW`, remote `github.com/asifuddin01/WINNOW` (public), branch
  `main`.
- **Read with:** [WINNOW_BUILD_GUIDE.md](WINNOW_BUILD_GUIDE.md) (the plan, Section 17
  phases), [CLAUDE.md](CLAUDE.md) (the rules), [CHANGELOG.md](CHANGELOG.md) and
  [docs/decisions.md](docs/decisions.md).

---

## 1. Snapshot

| What | State |
| --- | --- |
| Commit | `35c9a75` "Record the decisions behind ORCID sign-in and Zotero RDF import", plus the commit adding this file |
| Working tree | clean; `main` level with `origin/main` |
| CI on `35c9a75` | all green on 2026-09-26: backend, frontend, API types, end to end, security scans, production image build and scan, restore test |
| Scheduled restore test | passed 2026-10-01 (monthly cron) |
| **CI now** | **the security scan will fail on the next push to `main`**: PyJWT 2.14.0 has two advisories (PYSEC-2026-4141, PYSEC-2026-4183), fixed in 2.15.0. See section 6. |
| Open pull requests | four Dependabot PRs (#10–#13, opened 2026-10-14), all failing CI. See section 6. |
| Build phases | Phases 0–9 done, including Phase 9's optional items (ORCID sign-in, Zotero RDF import) |
| Deployment | not deployed. The production stack is ready; it is waiting for the owner's server. See section 7. |
| Local machine | Docker Desktop was not running when this was written; 18 GB free on the disk |

## 2. What Winnow is

A free, open-source, self-hostable platform for systematic, scoping and rapid reviews:
import, deduplicate, screen (title/abstract, then full text), resolve conflicts, extract
data, assess risk of bias, and report (PRISMA 2020).

- **Stack:**
  - Backend: FastAPI with async SQLAlchemy and asyncpg, Alembic, PostgreSQL 16, Redis 7, an
    ARQ worker, structlog.
  - Frontend: React with TanStack Router and Query, Tailwind with Radix/shadcn, i18next.
  - Serving and tests: Caddy, Docker Compose, Playwright, k6, OWASP ZAP, and age for
    backups.
- **Planned address:** `https://winnow.sandhiresearch.org`, for Sandhi Research Lab.

## 3. Completed work

All phases are recorded in CHANGELOG.md:

| Phase | What it built |
| --- | --- |
| 0 | Foundation |
| 1 | Accounts and security |
| 2 | Reviews, team and settings |
| 3 | Import and records |
| 4 | Deduplication |
| 5 | Title and abstract screening, blind mode, conflicts |
| 6 | Relevance ranking and AI suggestions |
| 7 | Full texts |
| 8 | Extraction, risk of bias, reporting |
| 9 | Polish, hardening, launch, plus the optional items |

Phase 9 delivered all of these:

- **Items 1–13:**
  - the command palette, notifications, presence and the instance admin panel;
  - the i18n setup;
  - accessibility audit fixes;
  - the performance audit (`make perf`) and k6 load test (`make load`);
  - the OWASP ZAP baseline, also in CI;
  - `docker-compose.prod.yml` and its `make prod-*` targets;
  - encrypted backups with rotation, plus a restore test (`make prod-backup`,
    `prod-restore`, `restore-test`, and `.github/workflows/restore.yml`);
  - docs/deploy.md and docs/user-guide.md.
- **Acceptance, all met** (docs/performance.md, docs/accessibility.md):
  - every Section 2.2 budget is met and reported, with two tails explained;
  - zero serious or critical axe findings;
  - ZAP shows no high-risk alerts;
  - the restore test passes;
  - the load test on the production stack: p95 37 ms, 0 errors in 19,920 requests.
- **Item 14** (the optional items), done after the owner asked:
  - Zotero RDF import;
  - sign-in with ORCID.

### Commits since Phase 9's write-up (`7467556`)

| Commit | What |
| --- | --- |
| `db3b997` | Finished Codex's rewrite of `NotificationsMenu.test.tsx`: two failing tests fixed; Codex has stopped, and its leftover work was finished rather than discarded |
| `ebeabfe` | Zotero RDF import |
| `0c49d9e` | Sign in with ORCID, for accounts that link their iD; Google and ORCID now share the OpenID Connect code |
| `35c9a75` | decisions.md and CHANGELOG entries for both |

### Files they touched

**`ebeabfe`, Zotero RDF:**
- **Added:**
  - `backend/app/parsers/zotero_rdf.py`
  - `backend/alembic/versions/2026_09_26_b7e1c2d4f5a6_zotero_rdf_imports.py`, which adds
    `zotero_rdf` to the `file_format` enum
  - `backend/tests/fixtures/parsers/zotero.rdf`
- **Changed:**
  - `backend/app/parsers/__init__.py` (registry, `.rdf` extension, content sniffing)
  - `backend/app/parsers/xml_reader.py` (`children_of_root`)
  - `backend/app/models/record.py` (`FileFormat.ZOTERO_RDF`)
  - `backend/tests/unit/test_parsers.py`
  - `backend/tests/integration/test_imports.py`
  - `frontend/src/features/imports/UploadCard.tsx`
  - `frontend/src/api/openapi.json`, `frontend/src/api/schema.d.ts`
  - `docs/user-guide.md`

**`0c49d9e`, ORCID:**
- **Added:**
  - `backend/app/security/oidc.py`: the shared OIDC client, `SignInError`, `OneTimeStore`,
    `pkce_pair`
  - `backend/app/security/orcid.py`
  - `backend/app/api/external_sign_in.py`: the steps after the provider answers, and the
    shared two-factor finish
  - `backend/app/api/v1/orcid.py`: `start`, `link`, `callback`, `DELETE` (unlink),
    `two-factor`
  - `backend/app/services/identities.py`
  - `backend/tests/security/test_orcid_sign_in.py`
  - `frontend/src/components/auth/OrcidButton.tsx`
  - `frontend/src/features/account/OrcidSection.tsx`
- **Changed:**
  - `backend/app/security/google.py`, `backend/app/api/v1/google.py`: now built on the
    shared modules
  - `backend/app/config.py` (`ORCID_CLIENT_ID`, `ORCID_CLIENT_SECRET`, `ORCID_BASE_URL`)
  - `backend/app/main.py` (`app.state.orcid`, `orcid_flows`, `pending_sign_ins`)
  - `backend/app/schemas/auth.py` (`ExternalSignedIn` replaces `GoogleSignedIn`;
    `UserOut.orcid`; `AuthOptions.orcid_enabled`; `OrcidLinkStart`)
  - `backend/app/api/session_http.py`
  - `backend/app/api/v1/__init__.py`, `backend/app/api/v1/auth.py`
  - `backend/app/security/rate_limit.py` (`ORCID_PER_IP`)
  - `backend/app/services/google_accounts.py`
  - two existing tests: `test_auth_flows.py`, `test_sessions_and_csrf.py`
  - frontend:
    - `api/auth.ts` (`startUrl`, `finishExternalSignIn`, `SIGN_IN_ERRORS`, `linkOrcid`,
      `unlinkOrcid`)
    - `routes/login.tsx`, `routes/register.tsx`, `routes/_app/account.tsx`
    - `lib/search.ts`, `test/api.ts`
    - the tests
  - `.env.example`, `README.md`, `docs/deploy.md`, `docs/user-guide.md`

### Verified before the last push

- **Backend:** 900 tests at 95% coverage. `ruff check`, `ruff format --check` and
  `mypy --strict` are clean over the whole backend.
- **Frontend:** 276 tests (36 files). Coverage is 89.3% statements, 80.3% branches and
  87.1% functions, all above the 85/70/85/85 thresholds. `tsc` and ESLint are clean.
- **In a browser:** checked headlessly with a fixture account (e2e-orcid-…@example.com)
  against a placeholder ORCID sandbox client:
  - the ORCID button and error messages on the sign-in page (light and dark, desktop and
    phone);
  - the Account page's linked and unlinked states.

  The dev API was restored afterwards and the scratch files deleted.

## 4. Decisions made in this stretch

The full reasoning is in docs/decisions.md, under "Phase 9".

- **ORCID is link-only.** ORCID shares no email address, so an iD signs in only to an
  account whose owner linked it from Account. It never creates or matches accounts.
- **ORCID uses OpenID Connect with a nonce, and no PKCE**, which ORCID doesn't support. The
  state is bound to the browser by a `__Host-` cookie.
- **A link finishes only in the session that started it.** This protects shared
  computers.
- **One iD per account and one account per iD.** Linking a new iD replaces the old one.
- **Two-factor still applies after Google or ORCID.** A sign-in started with one provider
  can't be finished at the other's endpoint (`pending["method"]` is checked).
- **`ORCID_BASE_URL` is restricted** to `https://orcid.org` or
  `https://sandbox.orcid.org`.
- **Zotero RDF:**
  - every top-level node with a `z:itemType` is a reference, except attachments and
    notes;
  - the journal or book a reference belongs to is read whether it is nested or pointed at
    (a two-pass read, only when needed);
  - DOIs and PubMed ids are also read from "Extra";
  - a name with no given name is kept whole.
- **Hosting:** Hetzner CX33 (4 vCPU, 8 GB, 80 GB; €8.49/month plus €0.50 for IPv4; hourly
  billing, no contract), in Nuremberg or Falkenstein, running Ubuntu 24.04.
  - Rejected:
    - Oracle's free tier (needs a credit card);
    - Cloudflare Pages/Workers/Containers and Vercel Hobby, which can't run the Python
      API, PostgreSQL, the worker, ClamAV or big uploads; Vercel Hobby's terms also allow
      only non-commercial use;
    - OVH, which needs a year paid upfront.
  - Later, the owner may move to a home server behind Cloudflare Tunnel: back up, restore
    at home, switch DNS to the tunnel, delete the Hetzner server. The tunnel option
    (about 20 lines in the prod compose file) isn't built yet.
- **DNS:** Cloudflare, with the `winnow` A record set to **DNS only** (grey cloud), because
  Cloudflare's free proxy caps uploads at 100 MB.
- **Email:** Brevo's free plan (300 emails a day), sending from a subdomain address such
  as `winnow@mail.sandhiresearch.org`, with SPF and DKIM set up in Cloudflare.

## 5. Errors met, and how they were resolved

| Error | Resolution |
| --- | --- |
| Codex's `NotificationsMenu.test.tsx` failed 2 of 3 tests | Discarding it was blocked by the permission check. Fixed instead: open the bell after the page settles; "Mark all as read" is a menu item, and it keeps the menu open (close it with Escape). |
| Zotero organisation authors were reversed ("Organization, World Health") | A name with no given name is kept as written |
| Two existing auth tests failed after adding ORCID | Added `orcid_enabled` to the options test, and listed `POST /auth/orcid/two-factor` as public (authorised by its pending cookie) |
| ruff: import order (I001); C416 in `identities.py` | Fixed with `ruff --fix` and `dict(rows.tuples().all())` |
| ESLint `prefer-nullish-coalescing` in `login.tsx` | `options && (options.google_enabled \|\| options.orcid_enabled)` |
| `pytest --cov=app.<module>` raised ImportError in conftest | Use `--cov=app` and filter the report instead |
| Docker CLI hangs on the macOS Keychain credential helper | Use `DOCKER_HOST=unix:///var/run/docker.sock`. For image pulls, set `DOCKER_CONFIG` to an empty directory whose config.json lists `cliPluginsExtraDirs`. |

## 6. Pending tasks, in order

1. **Upgrade PyJWT to 2.15.x on `main`.** This is a security fix and comes before
   deploying: PyJWT verifies the Google and ORCID ID tokens.
   - Run `uv lock --upgrade-package pyjwt` in `backend/`, then the checks in section 9.
   - Push, and confirm the "Security scans" job turns green.
2. **Deal with the Dependabot PRs.** None can be merged as they stand.
   - **#11, Python group:** brings PyJWT 2.15.1 and **SQLAlchemy 2.1.4**. SQLAlchemy 2.1
     changes how `Select` is typed, and mypy fails in `app/services/audit_log.py` (lines
     72, 94, 124, 144), `app/services/dedup.py` (179, 438–446, 534) and
     `app/services/accounts.py` (340). Either fix the typing for 2.1, or pin
     `sqlalchemy<2.1` and take the rest.
   - **#13, frontend group:**
     - **TypeScript 7.0.2** breaks `typescript-eslint` ("does not support TS 7.0") and
       `openapi-typescript` (`createKeywordTypeNode` undefined), which makes the
       "API types are current" job fail.
     - **ESLint 10** is in the group too.
     - Keep TypeScript at 6.x and ESLint at 9 (ignore those majors in
       `.github/dependabot.yml`), and take the rest.
   - **#12 (e2e) and #10 (GitHub Actions):** fail only on the shared PyJWT scan, plus
     TypeScript 7 and `@types/node` 26 in #12. Rebase them after task 1. Actions must stay
     pinned to commit SHAs.
3. **Deploy to Hetzner**, once the owner sends the server's IP. The runbook is in
   section 7.
4. **After deploying:**
   - run the ZAP baseline against the live site. `make zap` only scans the local stack
     (`http://caddy:8080`), so run its `docker run … zap-baseline.py` line without
     `--network`, with `-t https://winnow.sandhiresearch.org`, then
     `python3 security/zap_verdict.py zap-report/zap.json`;
   - set up the nightly backup cron and the rclone copy off the server;
   - register the ORCID production client, with redirect URI
     `https://winnow.sandhiresearch.org/api/v1/auth/orcid/callback`, and add its
     credentials to the server's `.env`.
5. **Later, only if asked:**
   - the Cloudflare Tunnel option, for the home server;
   - account deletion, which the guide describes but nothing implements yet.
     `users.deleted_at` is never set today. When it is built, decide what happens to
     `user_identities`.
6. **For the owner, outside the repo:** a portfolio write-up of Winnow was delivered on
   2026-09-26. Its temporary copy is gone; ask again if it needs regenerating.

## 7. Deployment state and runbook

**The owner has done:**
- **SSH key:** `~/.ssh/id_ed25519`, comment "winnow deploy", fingerprint
  `SHA256:GVRElEa+7mcqweFXWc7odVk2PL0PfwWhE5jT/EryqaY`, loaded into the macOS keychain.
  The public line to paste into Hetzner is in `~/.ssh/id_ed25519.pub`.
- **age:** 1.3.2, installed with Homebrew.
- **The backup key pair:** the private key is `~/winnow-backup.key` (mode 600; never read
  it, copy it, or put it on a server). The public key, for `AGE_RECIPIENT`:
  `age1qlx4wgtt58892j0d3sfvdfezlkrtj7kmps9xm82f32864tfqjupquy8kmn`.

**The owner still has to:**
1. Create the Hetzner CX33: Ubuntu 24.04, IPv4 and IPv6, the SSH key above. No Hetzner
   backups or volumes.
2. Add the Cloudflare **A** record: `winnow` → the server's IPv4, **DNS only**.
3. Set up Brevo:
   - add `sandhiresearch.org` as a sender domain, with its DNS records in Cloudflare;
   - create an SMTP key. The owner types it into `.env` themselves.

**Then Claude, over SSH from the Mac, following docs/deploy.md:**
1. Harden the server:
   - updates, and a non-root user in the `docker` group;
   - `ufw` allowing 22/tcp, 80/tcp, 443/tcp and 443/udp;
   - `PasswordAuthentication no`.
2. Install Docker Engine and the Compose plugin, and `age`.
3. `git clone https://github.com/asifuddin01/WINNOW.git /srv/winnow`.
4. **The `.env`:** the owner runs commands Claude provides. Don't write secrets yourself.
   - generated on the server: `SECRET_KEY`, `ENCRYPTION_KEY`, `POSTGRES_PASSWORD`;
   - `WINNOW_ENV=production`;
   - `PUBLIC_URL=https://winnow.sandhiresearch.org`;
   - `SITE_ADDRESS=winnow.sandhiresearch.org`;
   - the SMTP settings;
   - `AGE_RECIPIENT`;
   - `chmod 600 .env`.
5. `make prod-up`, then `make prod-create-admin email=… name="…"`. The owner types the
   password.
6. Set up `make prod-backup` in cron (02:15 nightly), plus rclone to off-server storage.
7. Check the result:
   - HTTPS loads, HSTS is sent, the health page is green;
   - ZAP baseline;
   - sign in, import a small RIS file, screen one record.

## 8. Rules that stay in force

From CLAUDE.md and the owner's standing instructions:

- **Security first.** Every project route uses `require_project_role`, and non-members get
  404. Blind mode is enforced in services. No raw SQL: `sqlalchemy.text` is banned by
  TID251.
- **Coverage stays at its floors:** backend ≥ 90%; frontend 85/70/85/85.
- **Types:** `mypy --strict` and `tsc` strict.
- **After any API change, run `make api-types`.**
- **The footer "Built by Asif"** (linking to https://asifuddin.com) stays on every page.
- **Small commits.** A CHANGELOG entry per phase; ambiguities go in docs/decisions.md.
- **Never commit the owner's private review corpus.** It is unpublished; it lives outside
  the repo, and its location is in Claude's memory.
- **Never handle the owner's passwords or secrets,** and never edit `.env` or
  `~/.docker/config.json`. Hand over validated commands instead.
- **Keep fixture data out of the owner's account.** Verify headlessly with
  `e2e-…@example.com` accounts. The built-in browser pane is signed in as the owner, so
  don't sign out of it or change that account.
- **Never delete audit rows.** For bulk deletes of user data, hand over SQL rather than
  running it; deleting e2e fixture projects is fine.
- **Clean up after every run:** fixtures, uploads, images, scratch files, test results.
  The disk is nearly full.
- **Codex has stopped.** Claude owns the whole queue and may commit, finish or replace
  Codex's leftovers.

## 9. Working notes for this machine

- **Start:** start Docker Desktop, then `make up` (it waits until healthy). The app is at
  http://localhost:8080 and Mailpit at http://localhost:8025.
- **Every Docker command:** prefix it with
  `export DOCKER_HOST=unix:///var/run/docker.sock`.
- **Checks run inside the containers.** `make check` runs lint, types and tests (all of CI
  except e2e). These are the exact commands, to run before every push:

  ```bash
  docker compose exec -T api sh -c "ruff check . && ruff format --check . && mypy && python -m pytest -q --cov=app"
  docker compose exec -T web sh -c "npx tsc --noEmit -p . && npx eslint src && npx vitest run --coverage"
  ```

- **pnpm:** use `npx --yes pnpm@12.5.1` (the host's corepack is too old). Only `make e2e`
  runs on the host; Playwright runs with 2 workers.
- **The worker** reloads on code changes. Restart it only after queued jobs drain.
- **CI:** `gh` is signed in as asifuddin01, so `gh run view <id> --log-failed` shows why a
  job failed. Anonymous API calls see only check-run annotations.
- **The code graph:** `graphify-out/` (git-ignored). Use `graphify query "…"` to find
  code, and rebuild it with `/graphify . --update` after large changes.

## 10. Next action

Upgrade PyJWT on `main` (task 6.1):

```bash
cd ~/Web/WINNOW/backend && uv lock --upgrade-package pyjwt
```

Then run the checks in section 9, commit "Upgrade PyJWT past PYSEC-2026-4141 and -4183",
push, and confirm CI is green. After that, work through the Dependabot PRs (6.2). When the
owner sends the Hetzner IP, follow section 7.

## 11. How to resume

1. Start Docker Desktop.
2. Open Claude Code (desktop app or `claude`) in `~/Web/WINNOW`.
3. Send: **"Read HANDOFF_last.md and continue from section 10."**
4. If the server is ready, send its IPv4 address instead, and say whether the Cloudflare
   record and Brevo are done.
