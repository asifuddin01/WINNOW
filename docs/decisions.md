# Decisions

Where the guide left a choice open, or a tool forced one, the choice and the reason are
recorded here (CLAUDE.md: "choose the more secure and simpler option and note it").

## Phase 0

### Versions
- **Runtimes follow the guide, libraries are the latest compatible.** Python 3.12,
  PostgreSQL 16, Redis 7 and Node 22 are named in the guide and kept. Libraries were the
  latest stable at build time, pinned in `uv.lock` and `pnpm-lock.yaml`.
- **TypeScript 6.0, not 7.0.** typescript-eslint supports TypeScript below 6.1 only; the
  type-aware lint rules matter more than the newer compiler. openapi-typescript declares
  TypeScript 5 but generates correct types with 6, so `pnpm-workspace.yaml` allows it.
- **ESLint 9, not 10.** eslint-plugin-jsx-a11y does not support ESLint 10 yet, and
  accessibility linting is a requirement (CLAUDE.md).
- **redis-py 5.x.** ARQ caps redis-py below 6. ARQ's `Worker.close()` calls a method redis-py
  deprecated, so the test suite ignores that one warning when it comes from ARQ; all other
  warnings are errors.

### Frontend
- **shadcn/ui 4, "vega" style, Radix base.** Radix is what the guide names. shadcn 4 uses its
  `cn` package (replaces clsx + tailwind-merge) and a CSS file from the `shadcn` package,
  which is a dev dependency because only the build reads it.
- **The generated sidebar was changed in three places:** it no longer writes a
  `sidebar_state` cookie (the API would receive it on every request; the shell keeps the
  preference in localStorage instead), its Ctrl/Cmd+B shortcut does not fire while typing
  (guide 11.4), and `SidebarInset` is a `<div>` so the page `<main>` and the `<footer>`
  are siblings (correct landmarks).
- **localStorage holds UI preferences only** (theme, sidebar state), through
  `src/lib/storage.ts`. ESLint forbids direct `localStorage`/`sessionStorage` use elsewhere.
- **The theme is applied before first paint by `public/theme-init.js`**, an external file
  rather than an inline script, so the strict CSP planned for Phase 1 (`script-src 'self'`)
  needs no exception.
- **Route layout.** The root route renders no chrome. Pages inside the app sit under the
  pathless `_app` layout (sidebar, top bar, footer); pages outside it (not found, errors, and
  later sign-in) use `StandalonePage`, which also renders the footer. The error and not-found
  components detect whether they are inside the shell, so the footer appears exactly once
  wherever an error happens.
- **Colours are tuned for long screening sessions,** at the owner's request. Neither theme
  uses pure white or pure black. Light is a matte, low-glare soft grey-white paper (`#E7E6E3`)
  with near-black text (`#181512`) at 14.5:1 instead of 20:1, and secondary text
  (`#413C38`) at 8.7:1 so it never looks faded; cards sit barely above the page so nothing
  glows. Brighter, creamier papers (`#F9F6F2`, then `#EEEAE5`) still felt like
  too much light. Dark is "night slate", a soft blue-grey
  (`#131B25`) with clear off-white text (`#EBE9E4`) at 14:1 instead of 19:1, secondary text
  at 9:1, a slightly heavier text weight (430) because light-on-dark text reads thinner,
  and a muted teal accent that does not glow. The neutrals are warm in light mode, not the slate the
  guide's branding note suggests. A flat warm grey dark theme felt "robotic", and a teal-green
  one was rejected. Every text colour still meets WCAG AA, body text meets AAA, and the
  Playwright axe checks cover both themes.
- **Phone navigation is a sheet in Phase 0.** The bottom tab bar in guide 11.2 is for the
  project navigation (five items + More); it arrives with projects in Phase 2.
- **The status banner uses `/readyz` and appears only on trouble** (offline, or the server
  cannot reach its database or Redis). A healthy app shows nothing.
- **Chromium only in Playwright for now** (desktop and phone viewports). Firefox and WebKit
  join when there is a user journey worth running in three engines.

### Backend
- **Secret validation applies in every environment,** not only production: startup fails on
  the `.env.example` placeholder, on a `SECRET_KEY` under 32 bytes, or on an
  `ENCRYPTION_KEY` that is not exactly 32 bytes of base64. `make env` generates both.
  Production additionally requires an `https://` `PUBLIC_URL`.
- **Errors are documented as `application/problem+json`.** FastAPI documents every body as
  `application/json`; the app rewrites its OpenAPI document so error responses carry their
  real media type and schema (`ValidationProblem` for 422). The generated frontend types
  depend on this.
- **Validation errors report location and reason, never the submitted value**, which could
  be a password.
- **Logs.** Uvicorn's access log is off; the request middleware logs one line per request with
  the route template (`/invites/{token}/accept`), not the raw path, so tokens in URLs never
  reach logs. httpx logs at WARNING because outbound URLs can carry API keys or contact
  emails. Request ids from callers are accepted only if short and plain.
- **No `text()` SQL.** ruff bans `sqlalchemy.text`; readiness uses `select(literal(1))`.
- **The first migration enables `citext`, `pg_trgm` and `pgcrypto`** (guide 6.3). All three
  are trusted extensions, so a database owner without superuser rights can create them.

### Infrastructure
- **Only Caddy is published, on `127.0.0.1:8080`.** PostgreSQL and Redis stay on the internal
  network (guide 12.7), which also avoids clashing with a PostgreSQL already on the host.
  To test on a phone over the LAN, change the Caddy port binding locally.
- **Development database password is `winnow`.** The database is reachable only on the
  Compose network. Production (Phase 9) will require a strong password.
- **Caddy forwards to Vite as `Host: web:5173`,** and Vite allows only that name, so the dev
  server answers however Caddy is reached (localhost, a LAN address) without opening Vite
  to arbitrary hosts.
- **Security headers now: nosniff, Referrer-Policy, X-Frame-Options, Permissions-Policy,
  COOP.** The Content-Security-Policy and HSTS from guide 12.5 come with Phase 1, which
  needs a development/production split for them (Vite's dev client needs a looser policy).
- **Make targets run inside the containers,** so a fresh clone needs only Docker and make.
  `make e2e` is the exception: Playwright runs on the host against the running stack.
  CI runs the same checks natively, with PostgreSQL and Redis as service containers.
- **Migrations run in a one-shot `migrate` service** that the API and worker wait for, so
  `make dev` always starts on the latest schema.
- **Deferred:** ClamAV and MinIO (and `make local` without them) arrive with uploads in
  Phases 3 and 7; dependency, secret and container scanning in CI arrive with Phase 1.
  Bandit's rules already run through ruff (`S`).

### Legal
- **License: AGPL-3.0**, as guide 19.3 recommends, so public modified deployments share
  their changes.

## Phase 1

### Accounts
- **Single-user mode is a first-run setup page,** not an account created behind the
  scenes. The guide says the mode "auto-creates one admin", but an automatic account needs
  a way to hand over its password, and the guide forbids passwords in logs. So while no
  account exists, `/setup` creates the administrator (already verified, no email) and signs
  them in; after that, setup and registration are closed. `make create-admin` creates
  verified administrators in any mode, for deployments.
- **Registration, sign-in and password reset never reveal whether an email has an
  account.** Registering an existing address answers exactly like a new one and emails the
  owner instead. Unknown emails still spend an Argon2 verification, so they take as long as
  a wrong password.
- **Locked accounts get the same "incorrect" answer,** and the owner is emailed when the
  lock starts (10 failures, 15 minutes). Wrong authenticator codes count toward the lock.
- **Unverified accounts can sign in** (guide 8.1 only bars them from joining projects); a
  banner offers a new link.
- **Email links need a click.** `/verify/{token}` asks the person to press a button:
  mail security scanners open links, and a link that confirmed itself on load would be
  spent before its owner saw it. Reset links need a new password anyway.
- **Password rules:** 12 to 256 characters, not the email address, and not in a known
  breach (Have I Been Pwned range API, padded, only 5 hex characters of the SHA-1 leave the
  server; fails open when the service is unreachable; `PASSWORD_BREACH_CHECK=false` offline).
  A show-password toggle replaces a "confirm password" box.

### Sessions and CSRF
- **Redis stores sessions under the SHA-256 of the cookie value,** so a Redis dump does not
  hand out working cookies. A per-user index lists devices and supports "sign out everywhere".
  Idle expiry is the key's TTL (7 days); absolute expiry (30 days) is checked on read.
- **New session id on sign-in, password change, and turning 2FA on or off.**
- **CSRF: signed double-submit plus Origin.** A random nonce lives in an HttpOnly
  `__Host-winnow_csrf` cookie; the token is HMAC(SECRET_KEY, nonce + session), fetched from
  `/auth/csrf` and kept in memory. Every write under `/api/v1` needs the token and an
  Origin (or Referer) equal to PUBLIC_URL's origin. Development must therefore be opened at
  PUBLIC_URL (http://localhost:8080), not at 127.0.0.1.
- **Secure cookies over plain HTTP work only on localhost,** which browsers treat as a
  secure context. Phone testing over a LAN address needs HTTPS.
- **Session expiry sends you to sign in and back.** Guide 11.6 asks for a modal that keeps
  the page; that belongs with screening (Phase 5), where unsaved work exists.

### Two-factor
- **TOTP secrets are encrypted with AES-256-GCM,** the user id as associated data, so a
  ciphertext copied onto another account does not decrypt. The last accepted time step is
  stored and codes are claimed with a conditional UPDATE, so a code cannot be replayed, not
  even by two racing requests.
- **Recovery codes are HMAC-SHA256 hashes, not Argon2.** They carry ~50 bits of entropy,
  are single-use and rate-limited; checking ten Argon2 hashes per sign-in would be slow for
  no gain. They are removed with an atomic `array_remove`.
- **Owners can be required to use 2FA** once projects exist (Phase 2); the instance setting
  arrives with the admin panel.

### Rate limits and audit
- **Sign-in limits count failed attempts only.** Guide 12.6 sets 5 per minute per IP and
  email and 20 per hour per IP. Counting every attempt would charge a two-step sign-in
  twice and throttle a university's worth of people behind one NAT address; the end-to-end
  test hit exactly that. Wrong passwords and wrong codes count; successes and the "enter
  your code" step do not. The limit is checked before any password work.
- **Sliding windows in Redis via one Lua script;** keys hold a hash of the IP or email, not
  the value. Limits from guide 12.6; verification and reset submissions share a 20/hour/IP
  limit so a mistyped password does not lock someone out of their own link.
- **The client IP is Caddy's X-Forwarded-For.** Caddy ignores the header from clients, and
  the API is reachable only through Caddy, so uvicorn trusts it (`--proxy-headers`).
- **The audit log is append-only by trigger,** which also binds the database owner the app
  uses in development. The separate production role with INSERT and SELECT only (guide
  12.8) comes with the production compose file in Phase 9.

### Headers, email, scanning
- **CSP from guide 12.5 on the app; `default-src 'none'` on the API.** Development adds
  `'unsafe-inline'` to `script-src` for Vite's hot-reload preamble (the `CSP_SCRIPT_SRC`
  variable); the production build has no inline scripts. HSTS is sent only over HTTPS. The
  development-only Swagger UI gets its own policy for jsDelivr.
- **Development email goes to Mailpit** (http://localhost:8025), whatever `.env` says, so
  links can be followed without real SMTP and never appear in logs.
- **CI security scans:** gitleaks over the whole history (with an allowlist of the exact
  fixture keys tests use), pip-audit, pnpm audit, semgrep (OWASP, Python, TypeScript and
  React rules), Trivy on the production images (fixable HIGH and CRITICAL). Dependabot
  opens weekly grouped updates. The one semgrep suppression is SHA-1 in the breach check,
  which the Pwned Passwords protocol requires.
- **The production web image serves the SPA with unprivileged nginx,** not Caddy. Trivy
  found fixable HIGH CVEs in the Go libraries inside `caddy:2-alpine`; a static file
  server needs no Go runtime to keep patched, and this image runs as a non-root user. The
  edge proxy is still Caddy; the production compose file (Phase 9) must pin a Caddy build
  that scans clean.

### Sign in with Google (added at the owner's request, 2026-09-22)
- **OpenID Connect, authorization code flow with PKCE, done on the server.** The browser
  follows a plain link to `/api/v1/auth/google/start`; no Google script loads, so the CSP
  stays `script-src 'self'`. A one-time `state` is bound to the browser by an HttpOnly
  cookie (login CSRF), a `nonce` ties the ID token to this sign-in, and PKCE makes an
  intercepted code useless. The ID token is verified against Google's published keys
  (RS256, issuer, audience, `azp`, expiry, nonce), and Google must say the email is verified.
- **Linking by verified email.** A Google identity (keyed by Google's stable `sub`, not the
  email) signs in as its linked account; otherwise it links to the account with the same
  email, which Google's verification proves the person controls, the same proof a
  password-reset link relies on. New addresses get a new account only when registration is
  open. Accounts created this way have no password (`NO_PASSWORD`, not a valid hash) until
  their owner sets one by email link.
- **Two-factor still applies.** A Google sign-in on a 2FA account parks in a five-minute,
  single-use record and asks for the code; wrong codes count toward the sign-in limit.
- **The callback's state cookie is SameSite=Lax,** because the browser returns from Google
  on a cross-site navigation; everything else stays Strict or Lax as before.
- **Off by default.** Without `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` the button is
  hidden and the routes answer 404. The flow is tested against a fake Google that signs
  real RS256 tokens; a live run needs real credentials.


## Phase 2 — reviews, team and settings

### Permissions
- **One check, one table.** `app/security/permissions.py` holds the role ranks and the
  capability table from guide 7; `require_project_role(min_role, flag=)` in `app/api/deps.py`
  turns it into the dependency every `/projects/{pid}` route declares, and the same table
  fills the `permissions` list in the project response, which the frontend uses only to hide
  controls. A test walks every project route in the OpenAPI document, so a route added in a
  later phase is covered the day it appears.
- **404 for outsiders, 403 for members.** A non-member (or a malformed id, or a deleted
  review) gets exactly the answer a review that does not exist gives, word for word. A member
  without the role gets 403: they already know the review is there.
- **Services take a verified membership, never a raw id.** Every method takes `ProjectAccess`
  and filters by `access.project_id`, so an id from another review is simply not found.
- **The owner is a row, and a unique index.** A partial unique index allows one owner per
  review; ownership moves only by transfer, which demotes the old owner to admin in the same
  transaction. Admins may manage everyone else, never the owner.
- **Reviewers and viewers may still leave, set their own preferences and copy a setup**
  into a review of their own; everything else in the review is read-only for them.

### Invitations
- **The token is the secret, and the address is the lock.** Only a SHA-256 of the token is
  stored. The invitation page is public, because the token is unguessable, but accepting
  requires a signed-in account whose *confirmed* email is the invited one, so a forwarded
  link is useless. The preview masks the address (`g•••@example.org`).
- **Re-inviting replaces the open invitation** (a partial unique index keeps one per address
  and review), invitations expire in seven days, and accepting is an atomic claim.
- **The link is returned once to the inviter,** so instances without SMTP can still invite;
  it grants nothing to anyone but the invited address.
- **Invite-only registration** accepts a registration carrying a valid invitation token for
  the same address; without one it stays closed.

### Reviews and their setup
- **Deleting a review is a soft delete**; it disappears for everyone immediately, and the
  rows stay for an administrator to recover. The typed confirmation is in the UI.
- **Colours are names, not CSS.** Keyword groups and labels store one of nine palette names;
  the frontend maps each to classes that work in both themes, so nothing a person types ever
  reaches a style attribute, and colour never carries meaning on its own.
- **Keyword patterns use a safe subset** (guide 12.3): literals, classes, `\d \w \s \b`,
  escaped punctuation, groups, alternation, anchors and quantifiers up to 100. No lookarounds,
  backreferences, named groups, inline flags or other escapes, and no repeating a group that
  itself repeats or alternates — the shape behind catastrophic backtracking. Patterns must
  also mean the same in JavaScript (with `u`) and Python, because both will run them.
- **Small collections are returned whole and capped** (criteria, keywords, reasons, labels,
  open invitations); cursor pagination is used where the list is unbounded — reviews and
  members. Ordering is by time-ordered UUIDv7 for reviews and by joining order for members.
- **Ordered lists keep dense positions.** Moving or deleting renumbers the siblings inside
  one transaction, so positions stay 0..n-1 per kind.
- **Settings are one JSON document with a pydantic model.** Unknown keys from an older
  version are dropped on read and defaults fill in new ones, so a settings change never needs
  a migration. Turning AI assist on is refused unless the instance has a provider.
- **Single-user instances** start reviews with one reviewer per record and refuse invitations.
- **Owning a review needs a confirmed email,** and two-factor authentication when
  `REQUIRE_OWNER_2FA` is on (guide 2.1); the instance-wide setting arrives with the admin panel.

### The frontend
- **The wizard creates the review at the end of step one** and then uses the very same
  editors as the settings pages, so nothing typed later is lost if the tab closes and there is
  only one implementation of each editor. The step lives in the URL.
- **Roles are enforced by the API; the UI reads `permissions`** to decide what to show, and a
  reviewer's settings pages are simply read-only.
- **Radix selects do not open on a jsdom click,** so component tests open them with the
  keyboard; buttons that pair an icon with a name carry an explicit `aria-label`.

## Phase 3 — Import and records

### Reading the files
- **The format is decided by the content, not the extension.** A `.txt` from PubMed is
  MEDLINE, a `.xml` may be PubMed or EndNote; each reader is asked whether the text looks
  like its format and the first confident answer wins.
- **Readers are generators** that yield either a record or a problem, so a 100,000-record
  file never sits in memory whole and one unreadable entry cannot end the import. XML is read
  with `defusedxml`'s streaming `iterparse` — entity expansion and external entities are
  refused, which the tests exercise with an XXE payload.
- **A record must have a title, a DOI or a PubMed id** to be worth keeping; anything else is
  reported as a problem with its line or entry number. The first 200 problems are stored; the
  count is exact.
- **Only the fields the six formats agree on are parsed.** Anything else is kept verbatim in
  `raw`, so nothing is lost and no reader has to guess.

### Getting them into the database
- **Imports are written with `COPY`** from the worker, in batches of 1,000. It is the only
  way to meet the guide's budgets (10,000 in under 10 seconds, 100,000 in under 60); the
  measured numbers are 2.4 s and 36 s.
- **`records.doi` is `text`, not `citext`.** asyncpg's binary `COPY` has no encoder for
  `citext`, and case-insensitive lookups use `doi_norm`, which is normalised anyway.
- **Generated columns call IMMUTABLE SQL functions** (`winnow_search_vector`,
  `winnow_authors_text`) because PostgreSQL will not accept `to_tsvector` with a
  configuration name or `array_to_string` directly in a generated column.
- **Memory is bounded by the upload cap,** not by the file's record count: the reader
  streams, the rows are batched, and a file larger than `MAX_UPLOAD_MB` is refused at the
  door with 413.
- **Confirming sets the batch to `parsing` before the job is enqueued,** so a second confirm
  arriving in the meantime cannot import the same file twice.
- **Undo removes the batch and its records in one statement** and leaves the file on disk for
  the retention job; the review's counts are recomputed, not adjusted.

### Reading them back
- **Search uses `websearch_to_tsquery` over the generated vector,** with the field filters
  parsed out first. A pasted DOI or PubMed id is recognised and answered exactly, because that
  is what someone pasting one wants.
- **Author search is a trigram index on a generated `authors_text` column.** Without it,
  `author:smith` was 209 ms on 100,000 records; with it, 32 ms.
- **Paging is by keyset,** with a cursor encoding the sort key and the id, so page 500 costs
  the same as page 1 and a record added mid-scroll cannot duplicate a row.
- **Facet counts are cached in Redis for five seconds.** They are a summary, not a source of
  truth, and recomputing them on every keystroke is what made them slow.
- **S3 storage is defined but not implemented** (`create_storage` raises for it). The guide
  lists it as optional and the interface is three methods wide when it is wanted.

### The frontend
- **The records table is virtualised** with a fixed row height and the next page is fetched
  as the end comes into view, so 100,000 records scroll like 50. jsdom lays nothing out, so
  the test setup gives elements a window-sized box; without it the virtualiser has a
  zero-height viewport and renders no rows.
- **Search, filters and order live in the URL,** so a link shares exactly what someone is
  looking at, and the browser's back button works as they expect.
- **Progress comes from the project's event stream,** which the import page uses only to
  invalidate queries — the numbers themselves still come from the API, so a missed event
  cannot leave the page telling a story the database does not support.

## Phase 4 — Deduplication

### The algorithm and who owns it
- **The pure engine is Codex's** (`app/dedup`, see `docs/codex-notes.md`); this phase adds
  the adapter around it — loading records, the blocking the database or the corpus has to
  do, the cluster tables, merging, the API and the screen. The one change to the engine is
  an `extra_pairs` keyword on `cluster()`, which Codex asked for.
- **RapidFuzz is not used.** The guide names `rapidfuzz.fuzz.token_sort_ratio`; the
  project takes no new dependencies for this, and `difflib.SequenceMatcher` over sorted
  tokens gives the same ordering of candidates for titles.

### Block C
- **The guide's pg_trgm block does not scale as an all-pairs join.** At 50,000 records the
  self-join ran for over two minutes, against a 30-second budget — and on a real
  8,278-record scoping review it ran past a minute on its own. A review is about one topic,
  so its titles share most of their trigrams and every index probe returns much of the
  table. Block C is therefore two things: an in-memory index over each title's distinctive
  words (shared by at least two records, used by no more than 300, and not in more than
  5 % of the corpus), which finds reordered and subtitled titles in about a second at that
  size; and the trigram join itself, only for reviews of up to 1,000 records, in its own
  transaction with a 5-second statement timeout, falling back to the word block if it runs
  out of time. On a real search the word block alone missed no duplicate.
- **Both only nominate pairs.** Every candidate is scored by the same function and guarded
  by the same DOI rules, so a looser block cannot merge anything on its own.

### Merging
- **Nothing is deleted.** The secondary keeps its row with `is_duplicate` and
  `duplicate_of`; PRISMA counts them, and the records list shows them with a filter.
- **Certain clusters merge themselves by default** (`dedup_auto_resolve`): an exact DOI or
  PubMed id, or a score of at least 0.98, with no conflicting DOI anywhere in the cluster.
  Everything else waits for a person. Deduplication after each import is also a setting
  (`dedup_on_import`), on by default, as guide 8.4 says "configurable".
- **"Not duplicates" is remembered** by storing the ignored cluster; a rerun skips any
  cluster with exactly the same members. A new record joining the group makes it a
  different group, which is asked about again.
- **A rerun replaces only pending clusters.** Decided ones are history.
- **Decisions, labels and notes move to the primary on merge** (guide 8.4) through one
  function, `migrate_work`. Those tables arrive with screening in Phase 5, so today it has
  nothing to move; it is the one place that will.
- **Merges are batched**: one `UPDATE … FROM (VALUES …)` for all secondaries, and bulk
  inserts for clusters. Merging 5,000 clusters one statement at a time was most of the run.

### Uploading several files
- **Up to 20 files per upload** (`MAX_UPLOAD_FILES`), in one request, so a drop counts
  once against the 30-uploads-an-hour limit in guide 12.6 and one CSRF token covers it.
  Each file is still its own import: PRISMA counts searches separately, and undo must be
  able to take one file back out.
- **The database is per file**, guessed from the file name and correctable, because one
  drop often mixes PubMed, Scopus and IEEE exports. The search date and string apply to
  the whole drop; they can be edited per import afterwards.
- **Caddy's body limit stays the backstop** for the whole request; the API still enforces
  `MAX_UPLOAD_MB` per file while it streams.

### What was measured, and on what
- **Precision and recall** are asserted in CI on the labelled fixture (errata, conference
  abstracts, accents, HTML, missing years), through the database. They were also measured
  on a real search: 18 overlapping arXiv queries from a scoping review, 637 records of 459
  papers, with the search's own provenance as ground truth — 98.97 % precision, 100 %
  recall. That corpus is the owner's unpublished work and is not in the repository.

### Running it on a real review
- **One dedup job per review, ever.** The job id is `dedup:<review>`, so arq refuses a
  second while one is queued or running; imports queue it 5 seconds after they finish, so
  a drop of twenty files makes one run. Because an import that finishes mid-run cannot
  queue its own, the run checks when it ends whether records arrived and goes round again
  (at most three passes). Before this, 38 imports started a dozen concurrent runs on one
  review, and the last to finish had started before the last import landed.
- **Identical copies are not a question.** Overlapping searches of one database return
  the same entry repeatedly; when such copies sit inside a group that needs a person
  (say five copies of an arXiv preprint and the published chapter), the copies — same
  normalised title, year, first author and source — are merged first as a certain group,
  and the person is asked only about what is left. Only when auto-resolve is on.
- **`duplicate_of` always names the record that was kept.** Merging a record that others
  were already merged into re-points them, so there are no chains to follow.
- **A preprint against its published version waits for a person,** even with the same
  title, because it differs in year, source and DOI — and whether those count as one
  record is the review's decision, not the software's.

### Event streams
- **A stream lives five minutes, then ends,** with a `retry:` hint; the browser reconnects
  and is sent the recent events again. An endless response kept uvicorn waiting for ever
  on reload and would do the same on a production shutdown or deploy, so uvicorn also has
  a graceful-shutdown timeout (5 s in development, 10 s in production).


## Phase 5 — Screening, blind mode and conflicts

### The queue
- **The queue is read from an index, not sorted per request.** Each record gets a random
  `sort_key` when it is inserted, indexed with its project. "Random" order starts each
  reviewer at their own point in that key (from a hash of their user id) and wraps round,
  so two reviewers do not meet the same records in the same order, and the next page is
  one index range scan. "Relevance" serves scored records first, then the same rotation.
  Sorting 100,000 records with `ORDER BY random()` took 660 ms at p95; this takes 15.
- **The queue does not say how many are left.** Counting what remains is the expensive
  half of the query; the progress bar has its own endpoint and is refreshed after
  decisions, not with every page.
- **The browser holds ten records ahead** and asks for more when five remain, sending the
  ids it already holds so they are not served twice. A decision moves to the next record
  before the server answers; a refusal puts the record back with the reason.
- **Decisions made offline are kept in memory, not in browser storage,** and sent when the
  connection returns (or every ten seconds). Closing the tab would lose them, so while any
  wait the page shows how many and the browser asks before leaving. Nothing about a review is written to `localStorage`.

### Decisions
- **Reasons are kept only on an exclusion.** Choosing reasons and then including drops
  them, so a reason never explains the wrong decision.
- **Time is added up across visits and capped at 30 minutes per visit,** so a tab left
  open overnight does not become a record that took nine hours. It counts only while the
  page is visible.
- **Full-text maybe is pending,** not a separate status: full text has to end in include
  or exclude, so maybe there only means "not yet". The review's `maybe_counts_as` setting
  is for titles and abstracts (guide 6.4) and does not reach full text: there all maybes
  wait, and a maybe beside an include or an exclude is a conflict for a resolver.
- **Changing the number of reviewers or how maybe counts recomputes every status** for
  that stage, in batches of 5,000, one `UPDATE` per outcome.

- **Ids made in the same millisecond keep their order.** `uuid7()` carries a 12-bit
  counter after the timestamp (RFC 9562, method 1), so the records of one file, which
  get their ids within a few milliseconds, sort by id in the order they were read.
  "Import order" in the queue is that sort. Before, the bits after the timestamp were
  random, and a file's records came back shuffled within each millisecond.

### Assignment
- **Split assignment needs no table.** A record belongs to the N reviewers whose hash of
  (record id, user id) is lowest — rendezvous hashing. It spreads records evenly, needs no
  job when the team changes, and moves only the records of someone who joins or leaves.
- **In split mode anyone who screens may still decide any record** they open from search
  or history; the queue only chooses what to offer. Refusing would stop someone taking
  over a colleague's share, and the extra decision just counts towards the total.

### Blind mode
- **Enforced in the services.** A blinded caller's queue, record, records list, counts,
  filters and history are built without anyone else's decisions. The records list shows
  their own decision where the status would be, so the status column cannot show that two
  people disagree. Its filters and counts use their decisions too, and are cached per user.
- **Other people's labels are hidden; team notes are not.** Labels often carry a decision
  ("probably include"); a team note is something written for the team to read.
- **Owners and admins see through blind mode by default** (guide 12.2) and can choose to
  stay blind for their own screening. Conflicts are counted only for someone who can see
  or resolve them.
- **Decisions are never sent over the event stream,** so it cannot leak them.

### Conflicts and bulk decisions
- **A resolution is its own row** (`conflict_resolutions`, one per record and stage), not
  a change to anyone's decision; both decisions stay as they were made, and the status
  follows the resolution. It can be changed only while the record is still in conflict
  or was resolved as a conflict.
- **"Ask them to discuss" leaves a team note and emails the other reviewers** of that
  record, with a link to it. Nothing else is sent.
- **Bulk decisions are resolutions with source `bulk`,** so they sit above the reviewers'
  decisions without faking any, and are audited as bulk. The request carries the count
  the admin was shown; if the search now matches a different number, nothing changes and
  the new count comes back (409), so no one excludes records they did not see.

### The frontend
- **Keyword highlighting runs in the browser** on the record's text, with every plain term
  escaped, word edges that count accented letters as letters, a time budget per pattern
  and a cap on how much text is searched, so a slow pattern cannot freeze the page.
- **Shortcuts are the guide's defaults and cannot yet be changed.** Custom bindings are a
  setting for later; they would need to be stored per user and checked for clashes.
- **Swiping works only with touch,** and "maybe" only from the card's handle, so scrolling
  a long abstract cannot decide it. The buttons under the card always do the same thing.

## Phase 6 — Relevance ranking and AI suggestions

### Dependencies
- **scikit-learn (with NumPy and SciPy) joins the backend,** as the guide's stack names it
  for 9.2. Codex's modules stay dependency-free; ranking is not one of them, and a
  pure-Python logistic regression could not score 50,000 records in the budget.
- **The Anthropic Python SDK joins the backend** for the `anthropic` provider (guide 8.11).
  The `openai_compatible` provider (a local model, such as Ollama) is plain HTTP through
  httpx; no OpenAI package is added.

### The model
- **As guide 9.2 specifies** (TF-IDF title ×2 + abstract + keywords, 1–2 grams, sublinear,
  min_df 2, 100k features; logistic regression, balanced, C = 1, liblinear). English stop
  words were tried and did not help on the benchmark; they are not used.
- **No record is scored by a model that saw its own label.** Records that are labelled
  but still waiting for someone (a second reviewer, or a third in "all" mode after two
  agreed) are scored by 5-fold cross-fitting. Otherwise a blinded reviewer would see a
  record pushed to the top because another reviewer included it — a leak of blind mode
  through the order (guide 8.6). The out-of-fold scores also give the cross-validated AUC.
- **The fitted model is not stored.** Every run refits from the decisions; `artifact_key`
  stays empty, so nothing is ever unpickled.
- **The TF-IDF corpus is cached in the worker's memory** (two reviews), keyed by the
  number of records and the newest id, so it is rebuilt when an import lands or is undone.
  Building it is the slow part (27–50 s at 50,000 records) and happens in the background
  after an import; the queue is usable meanwhile.

### When it trains
- **Guide 8.10's schedule:** the first model (see below for when); then after every 25 new
  decisions, at most once a minute per review and stage,
  and on demand. A Redis counter per review and stage counts decisions; the job takes off
  what it covered, so decisions made during a run still count towards the next.
- **The first model now comes with the first include and exclude, not 5 of each**
  (owner's decision, 2026-09-25, departing from guide 8.10). On sparse reviews the random
  warm-up before five includes was most of the work (Bos 2018: 2,291 records to 95% recall
  against 699); across 21 reviews the median saving rose from 55% to 63%. With one include,
  a record that is labelled but still waiting for another reviewer cannot be cross-fitted,
  so it is left unscored until there are two of each rather than scored by its own label.
- **Imports queue a run,** so new records are ranked in. Anyone who screens may ask for a
  retrain; it is debounced like the rest.

### Scores live in their own table
- **`record_scores (record_id, stage, project_id, score)`, not `records.relevance_score`.**
  Each run rewrites every score in the review; on `records`, each write also rewrote the
  row's ten indexes (three GIN), 13–17 s of a 19 s run at 50,000 records. The narrow table
  is replaced in one DELETE and one COPY (under 2 s), then ANALYZEd: with no statistics the
  planner answered "best first" by sorting the whole review (214 ms instead of 17 ms).
- It also keeps title/abstract and full-text scores apart, where one column mixed them.

### Relevance order in the queue
- **One in 20 served records comes from the reviewer's random order** (guide 9.2), counted
  across everything the reviewer has been served (their decisions plus the records held on
  screen), so the share is exact and the order stable across refills. The order control's
  hint says so, which is the disclosure the guide asks for.
- **With ranking off, "relevance" is the random order.**

### What people are shown
- **A blinded reviewer sees that a model exists and when it was trained, not the team's
  counts or AUC,** which are aggregates of other people's decisions (guide 8.6).
- **The recall curve** shows the viewer's own screening, and the team's (records in order
  of their first decision) to those allowed to see others. A dashed line shows the same
  finds at an even pace — what random order gives on average.
- **The stopping helper** speaks only with ranking on, a model trained and the rule
  reached, and says it is advice. Its estimate is computed at most once per 25 decisions
  and cached.

### The stopping estimate
- **Only the decisions made in relevance order count.** Decisions before the stage's first
  model were served in random order, at a steady rate of finds; fitting them made a
  reviewer who had found all 37 includes of a review read "about 25 left" (seen in the
  headless demo, not in the range-only check). They are left out.
- **Fitted twice and spanned.** A decaying Poisson rate fitted to the ranked decisions and
  to their recent half; the range spans both 90% bootstrap ranges, its top widened by two
  Poisson standard deviations, and the headline is the larger estimate, kept inside the
  range. Measured on the benchmark: 96% of ranges held the true number left (4% fell
  short), headline off by 0.8 at the median. Earlier versions: recent half only, 72%
  (20% short); recent plus whole history, 87% with headlines off by 6 at the median.
  Methods in `docs/methods.md`; replay with `benchmarks/stopping.py`.
- **The fit is closed-form plus bisection,** not a general optimiser: the first version
  took 24–66 s per estimate with its bootstrap; this takes under 0.2 s.

### AI suggestions
- **The provider is set in the environment** (guide 16.1's `LLM_*`), never stored in the
  database, and is available only when it has what it needs (a key for Anthropic, a URL
  and a model for a local one).
- **Only the owner can turn it on for a review** (guide 8.11); anyone who may change the
  settings can turn it off, the safer direction.
- **Claude Opus 5 by default** (`LLM_MODEL` overrides), structured JSON output held to a
  schema and validated again on the way in, low effort (a short judgement; the reviewer is
  waiting), and the API's refusal fallback. Out-of-range numbers are clamped and unknown
  criteria dropped rather than trusted.
- **Asking is limited to 60 an hour per person** (guide 12.6) and only counts when the
  provider is actually asked; seeing a stored answer asks nobody.
- **Suggestions are private to the asker while screening**; owners and admins can export
  them all (CSV, formula-safe), with each reviewer's own decision beside them.
- **Only the fact of asking is audited**, not the answer.

### Found along the way
- **`records.duplicate_of` had no index.** Deleting a record makes PostgreSQL look for the
  records merged into it, so deleting a 50,000-record review (or undoing a large import)
  scanned the table once per record: over ten minutes. A partial index on the duplicates
  makes it 5 s.

## Phase 7 — Full texts

### Scanning
- **ClamAV runs as `clamav/clamav-debian:1.4`** (the Alpine image has no arm64 build),
  under a compose profile the Makefile always enables. `make local` leaves it out for
  low-memory laptops; PDFs are then stored with scan status `skipped` and the app says
  they were not scanned. "Unscanned" is never shown as "clean".
- **The client speaks clamd's INSTREAM protocol directly** (a command, length-prefixed
  chunks, one answer): no client library, and anything but `OK` or `… FOUND` counts as the
  scanner being unavailable, never as clean. The scan job retries six times, waiting
  longer each time (clamd reloads its signatures on start); after that the PDF is marked
  `error` and stays closed.
- **A flagged PDF is moved to `quarantine/`, not deleted**, so what happened can be shown;
  the row keeps its signature, the owners and admins are emailed (without the file's
  name, which people type), and the event is audited. Anyone screening may replace it.
- **The EICAR test.** ClamAV flags EICAR only when it is the whole file: a PDF that merely
  starts with the string passes. The bare EICAR file is not a PDF and is refused at upload
  (magic bytes) before it is stored; the acceptance test is guide 12.10's "malicious PDF",
  a real PDF carrying EICAR as an attachment, which ClamAV unpacks and flags. CI runs the
  real clamd for it (`WINNOW_REQUIRE_CLAMAV=1`); elsewhere that one test skips when clamd
  is absent, and a stand-in scanner covers the flow.

### Reading and serving PDFs
- **Links last five minutes, are bound to the person who asked, and may be reused within
  that time** (pdf.js and downloads may fetch twice). They live in Redis; the file is
  streamed by the API, `inline` for the viewer and `attachment` for downloads, with
  `nosniff` and `no-store`. Another member, or someone signed out, gets 404 or 401.
- **Text and page count are read with pypdf in the worker** after a clean scan, capped at
  500 pages and 2 million characters, NUL characters removed (PostgreSQL text cannot hold
  them). A PDF pypdf cannot read is still kept and shown.

### Who may do what
- Reading PDFs and highlights: everyone in the review. Adding a PDF, looking for a free
  copy, highlighting and "not retrievable": anyone who screens (it is part of screening
  the full text). ZIPs of many PDFs: owners and admins, like search exports.
- **A PDF someone may be reading or has highlighted is replaced or removed only by whoever
  added it, or an owner or admin.** A quarantined or unscanned one anyone screening may
  replace.
- **Highlights are blinded like decisions** (a comment can carry a judgement): under blind
  mode a reviewer sees only their own.
- **Upload limits.** Guide 12.6 allows 30 uploads an hour. That stays for search exports
  and ZIPs; single PDFs have their own 300 an hour, because a full-text stage of a few
  hundred records is attached one PDF at a time. Looking up and fetching free copies is
  limited to 120 an hour (it asks outside services).

### Not retrievable
- **A mark of its own** (`unretrievable_records`), not a decision: the record leaves the
  full-text queue, its status becomes `not_retrievable` (PRISMA's "reports not
  retrieved"), and deciding on it is refused until the mark is undone. A conflict
  resolution still wins over the mark, and a PDF added later clears it.
- **New reviews no longer get the default exclusion reason "Full text unavailable"**
  (guide 8.2 lists it). It did the same job as this mark but counted the report as
  excluded, where PRISMA 2020 counts it as not retrieved; with both on offer, the numbers
  would depend on which a reviewer happened to pick. The owner's call ("do the best").
  Existing reviews keep their reasons: an owner can remove it under Settings → Exclusion
  reasons.

### Deleted reviews
- **A deleted review is hidden, not purged: its records, decisions, PDFs and every other
  piece of progress stay**, with no expiry (the owner's call). `sweep-files` removes only
  files no row refers to, so a deleted review's PDFs are never swept.

### ZIPs of PDFs
- **Checked before anything is unpacked:** at most 1,000 files and 2 GB in all, no entry
  over 100 times its packed size (checked on entries over 1 MB, so a tiny repetitive file
  is not mistaken for a bomb), no absolute paths, drive letters, `..`, NUL or symlinks.
  Refused with `zip_rejected` and an audit row. Extraction then counts the bytes it really
  gets, since sizes in a ZIP's headers can lie. Mac Finder's `__MACOSX/`, `._` and
  `.DS_Store` are skipped.
- **Matching by file name**, first against records at full text, then any record: DOI,
  PMCID, PMID or arXiv id ("sure"), then first author and year, with title words deciding
  between an author's papers that year, then title ("likely"). **A person confirms every
  match**; nothing is attached before that, and each PDF is scanned once attached. The
  arXiv id is read from the DOI, the abs link or the journal field: arXiv's own exports
  carry no DOI (found on the owner's review).
- **Unconfirmed ZIPs are discarded after a day** (hourly job), and can be discarded at
  once. Attached PDFs keep the storage key they were unpacked to.

### Free copies
- **Unpaywall by DOI (it needs `UNPAYWALL_EMAIL`) and PubMed Central by PMCID.** PMC's
  PDFs come from its public open-access bucket (`PMCnnn.v/PMCnnn.v.pdf`, latest
  version): Europe PMC's PDF render answered 403 and NCBI's `oa.fcgi` 404 when tried.
  Only the article's own file is taken — the folder also holds supplements under the
  publisher's names, and an early version fetched one of those on the owner's review.
- **The browser never sends a URL.** It picks one of the candidates the server just found
  (kept 10 minutes, per person and record) by id; the server fetches it: https only, every
  address the name resolves to must be public, the address actually connected to is
  checked again (DNS rebinding), redirects are followed by hand (at most five, each
  checked), a size cap, and the PDF's magic bytes after. Publishers that refuse servers
  (Wiley answered 403) are reported as such.

### The viewer
- **pdf.js's own viewer component**, not a hand-built renderer: text layer, search,
  lazy page rendering and zoom come with it. It is its own chunk (~180 KB gzipped), loaded
  only when a PDF is opened; the initial bundle stays at 154 KB.
- **No PDF JavaScript, no forms**: no scripting manager, annotation mode `ENABLE` (links
  only, opening in a new tab with `noopener`). **WebAssembly is off**: the CSP does not
  allow it, so pdf.js decodes JPEG 2000 and JBIG2 images without it, slowly or not at all.
  CMaps are not shipped; a PDF with non-embedded CJK fonts may show boxes.
- **Keywords and highlights are drawn in an overlay of their own** under the text layer,
  positioned as fractions of the page, so zooming never moves them and selection and
  search keep working. A highlight is made by selecting text and choosing a colour.
- **nginx now serves `.mjs` as JavaScript.** pdf.js's worker is an ES module; nginx's MIME
  list maps only `.js`, and browsers refuse a module worker served as
  `application/octet-stream`. Development (Vite) never showed it; checked on the
  production image.

### Pages
- **Full-text screening is `/p/:pid/screen/ft`** (guide 11's route map), the record's PDF
  beside the decision; the stage's PDFs, the list of records with their PDF's state and
  the ZIP flow are the same route's `?view=pdfs`, since the route map has no page of its
  own for them. Viewers get only that view. On a phone there is no swipe at full text
  (the PDF scrolls); the decision bar stays below it.
- **The next record's PDF is fetched while this one is read**, and PDFs are held a minute
  in memory for going back.

### Found along the way
- **Recomputing full text made records excluded at title and abstract "pending"** instead
  of "not eligible" (Phase 5). Only records included at title and abstract are
  recomputed now.
- **Merging duplicates left a copy's PDF behind**, out of view. It now follows to the
  record kept (with its highlights), unless that record has its own; so does a "not
  retrievable" mark. A ZIP entry matched to a record that was merged before the ZIP was
  confirmed goes to the record kept.
- **`make up` left a `node_modules` volume behind on every start** (`--renew-anon-volumes`
  renews them without removing the old ones): 14 of them, 3.1 GB, on the development
  machine. The web container is now removed together with its volume before each start.
- **The development machine's disk was 98% full** during the real-corpus run; macOS purged
  its caches and the API stalled for ~30 s. With space freed, the same run kept the
  health check at a median 40–85 ms.

## Phase 8 — Extraction, risk of bias, reporting

### Row-level security (guide 12.2)
- **The app logs in as the database owner, a superuser, which row-level security never
  binds.** So requests switch, at the start of every transaction, to `winnow_app` (no
  login, not a superuser, no BYPASSRLS) with the signed-in user's id in `app.user_id`,
  both local to the transaction so nothing outlives it on a pooled connection
  (`app.db`). On `records`, `decisions` and `notes` (the tables the guide names) that
  role reads and writes only rows of reviews the user belongs to. A query that forgets
  its review filter, or a row moved into another review, is stopped by the database; an
  unauthenticated request sees none of these rows at all.
- **Workers, operator commands and migrations stay the owner, deliberately.** They act
  for the system, not for a person, and PostgreSQL refuses COPY into a table under
  row-level security, which imports rely on. Every non-request session says so
  explicitly at each transaction.
- **The role cannot change or delete audit rows** (guide 6's "REVOKE UPDATE, DELETE from
  app role"), beside the append-only trigger.
- **Defense in depth, not the boundary.** An attacker who could run SQL could `RESET ROLE`;
  the guard is against mistakes in the app's own queries, which is what it is for.
- **The cost, measured at 100,000 records:** list and search p95 45–62 ms (budget 150),
  sort by title p95 124 ms (76 without), screening queue p95 14 ms (budget 80). Filters
  that PostgreSQL cannot prove leak nothing (full-text matching) are checked after
  membership, which keeps them off some indexes; the policy's membership list is worked
  out once per query. Sorting by title is the case to watch.
- **The role belongs to the server, not the database:** the migration creates it only if
  missing, and a downgrade revokes its rights but leaves it (the test database uses it
  too). An installation whose database user cannot create roles must create
  `winnow_app` first.

### PRISMA 2020 (guide 9.4)
- **Counted from the review, never typed in**, except what Winnow cannot know: records
  from other sources (citation searching, websites) and records removed before screening
  for other reasons. Owners and admins enter those. Codex's `app.prisma` checks that the
  boxes add up; a flow that does not is reported as `prisma_inconsistent` (422) rather
  than drawn wrong.
- **Databases are grouped by name however it was typed** ("pubmed", "PubMed "), so the
  identification box does not list one database twice.
- **Full-text numbers count only records still included at title/abstract**, so a record
  sent back to exclusion after its PDF was found does not stay in "reports assessed".
- **One reason per excluded report** (PRISMA lists each report once): a resolution's
  reason first, then the reviewers'; among several, the one listed first in the review's
  reasons. An exclusion with no reason is counted under "Reason not recorded" rather
  than dropped, so the boxes still add up.
- **An unfinished stage makes the diagram a snapshot**: the API says how many records
  still wait at each stage, so the page can say so beside the diagram.
- **Images are drawn from the same SVG**: PNG at 300 dpi with the resolution written
  into the file (so it prints at the intended size), and PDF, through CairoSVG in its
  safe mode (no external files or URLs are read while rendering).

### Screening statistics (guide 9.3)
- **Agreement is only for those allowed to see others' decisions.** Kappa between two
  people reveals how often they disagreed; a blinded reviewer sees only their own
  progress and pace. The rule sits in the service, like every other blinding rule.
- **Cohen's kappa per pair of reviewers, over the records both decided; Fleiss' kappa
  when the review asks for three or more reviewers per record, over the records that
  have exactly that many decisions** (Fleiss needs the same number of raters for every
  subject). "Maybe" is its own category when the review keeps maybes as maybes, and counts
  as include when the review moves them on, so agreement matches how decisions count.
- **Kappa is `null` when it cannot be calculated** (no shared records, or everyone used
  one category), never 0 or 1 by convention.
- **Checked against a hand-calculated review, scikit-learn's `cohen_kappa_score`, and
  the Fleiss formula written out independently in the test.**

### Risk of bias (guide 8.13)
- **Assessed per person, per study, per tool, and blinded like decisions.** Only studies
  included at full text can be assessed. Drafts may be partial; a submitted assessment
  judges every domain (and both axes for QUADAS-2).
- **Each assessment stores its tool's version and variant**, so a later edition of a tool
  never reinterprets saved judgements.
- **The plots use one final assessment per study**: the only submitted one, or the one
  chosen by someone who may resolve conflicts. Changing an assessment clears that choice,
  and studies still waiting for one are listed rather than silently dropped.
- **robvis's colours, and a symbol in every cell**, so the traffic-light plot never
  relies on colour alone. Newcastle–Ottawa is drawn as stars, as it is scored.

### Audit log viewer (guide 12.9)
- **Owners and admins only**: the log holds people's email addresses and IP addresses.
- **A reader who is blind to others' decisions sees that someone decided, and when, but
  not what**: the before/after of decision, conflict, risk-of-bias, AI-suggestion and
  extraction entries are withheld from them, in the service and the CSV alike.
- **The CSV streams**, so a long history never sits in memory, and every cell is
  formula-safe.

### Exports (guide 8.16, 10)
- **Every role may export, as guide 7 says; a full backup is the owner's alone.** A backup
  holds everyone's decisions and everyone's email address, and restoring it creates a
  review, which is an owner's act.
- **An export holds what the records table would show the person who asked**, with the
  same filters, and blinding applies: a blinded reviewer's file has their own decisions,
  reasons and labels, never the review's status computed from others'.
- **Made in the worker, acting as the person who asked**, under row-level security like a
  request, and their membership is checked again when it runs: someone removed from the
  review before their export is made does not get it.
- **Yours alone, for a day.** Another member cannot see or download it; files and rows
  are removed after 24 hours (failed and never-run jobs too). Asking and downloading are
  both in the audit log.
- **Spreadsheets cannot run anything.** CSV cells that start like a formula get an
  apostrophe; XLSX cells are written as text, so `=HYPERLINK(...)` stays words. Cells
  are cut at 32,000 characters with an ellipsis (Excel's limit is 32,767) rather than
  making a file Excel refuses to open.
- **RIS and BibTeX wait for Codex's writers** (`app.exports`); until they land, asking
  for them fails with a plain message rather than a half-made file.

### Full backup and restore (guide 8.16)
- **A ZIP of JSON lines, one file per table, plus the files.** `manifest.json` (format,
  version, row counts, files), `project.json`, `people.json`, `tables/<table>.jsonl`,
  and `files/imports/…` and `files/pdfs/…`. Rows are written from their columns, so a
  column added later travels without changing the exporter; the format has a version
  for the day it must change.
- **PDFs the scanner has not cleared are left out**, row and file: a backup never carries
  a quarantined file. A PDF missing from storage is noted in the backup and restored as
  an empty placeholder rather than failing the whole backup.
- **A restore is a new review, never a merge.** Every id is replaced, so a backup can be
  restored twice, or beside its original, and can never write into another review. It
  is titled "… (restored)" and belongs to whoever restored it.
- **The backup is untrusted input.** The ZIP is checked before it is read (entries,
  names, total size, and a 200:1 ratio: real backups compress 14–16:1, a bomb about
  1,000:1). Only known tables and columns are accepted; every value is typed by its
  column; every reference must point at a row of the same backup; settings and the
  review's description pass the same validation as a review created here. Anything
  else stops the restore with a message saying where, and nothing is kept.
- **Nobody gains access through a backup.** The person restoring becomes the only member.
  People in the backup are matched to existing accounts by email (their work stays
  theirs) or become placeholders under `.invalid` addresses that cannot sign in or
  receive mail, so a backup can neither create a working account nor add anyone.
- **The new owner starts blind**, like any owner; they see the team's work once they
  switch "Keep me blind too" off.
- **PDFs are scanned again** before anyone can open them, as on upload.
- **Measured at 100,000 records and 100,000 decisions:** backup 8.5 s (10.6 MB), restore
  40 s, both in the worker.

### Citation files: RIS and BibTeX (guide 8.16)
- **Decisions go where reference managers keep them.** RIS: `N1` notes ("Title/abstract:
  excluded (Wrong population)", labels, the Winnow id) and the custom fields `C1`–`C4`
  (statuses, reasons, labels). BibTeX: the `note` field. A blinded reader's file says the
  decisions are their own. "Not eligible" at full text (the record never got there) is
  left out of the notes, since every record excluded at title/abstract would carry it;
  the status field still has it.
- **The PubMed id is written as an accession number (`AN`) with `DB  - PubMed`**, as Ovid
  does, so reference managers and Winnow read it back as a PubMed id.
- **What Winnow writes, Winnow reads back**: both formats are tested through Winnow's own
  readers, which is why the BibTeX reader learnt LaTeX's escaped special characters.
- **BibTeX keys are the first author's surname and the year, ASCII only**, then `a`, `b`
  … `aa` on clashes, unique across the whole file even though it is written in batches.
  Other text stays UTF-8, which biber and current BibTeX read.

### Methods text (guide 8.15)
- **Only what the review holds.** Every fact is optional and a missing one drops its
  sentence: no agreement sentence without decisions to compare, no "blinded" for one
  reviewer, no full-text paragraph before there is a full-text stage.
- **A blinded reader's text leaves out what the team did together** (agreement, how
  disagreements were settled, work done in duplicate), as the statistics do.
- **Disagreements settled by one of the record's own reviewers count as "by discussion";
  by someone who had not decided it, as "by a third reviewer".** Winnow does not record
  a discussion as such, and this is the honest reading of who settled it.
- **Several pairs of reviewers give Cohen's kappa as a range**, not an average of kappas,
  which has no clear meaning.
- **Edited in the page, never saved**: the paragraph is a starting point to copy into a
  manuscript, and the numbers underneath change until screening ends (the page says so).
- **Screening stopped early by the stopping rule is not claimed**: Winnow only advises
  (guide 8.5) and records no stop, so the sentence exists but is never filled in yet.

### Data extraction (guide 8.12)
- **A form's versions share a family: the first version's id.** Entries belong to the
  exact version they were made on; a published version never changes, so exports and
  consensus always read data with its own form.
- **Only a draft can be edited or deleted; only the newest published version starts the
  next one**, and a family has at most one draft at a time.
- **An empty value is absent.** Text is trimmed, "12", 12 and 12.0 are one number, a
  multi-select is kept in the form's order, and an empty table row is dropped, so two
  extractors who typed the same thing never "differ".
- **Drafts may be partial; a submission is complete.** Required fields and a table's
  fewest rows are checked on submission only.
- **Dual extraction is set per form.** With it, whoever may resolve conflicts reconciles:
  the consensus starts from what every extractor agreed on, and each difference can be
  taken from either side. Saving it marks the entries it reconciled "verified"; changing
  an entry afterwards makes it "submitted" again, so the change shows.
- **Blinded like screening, in the service and in the database.** A blinded reviewer sees
  and exports only their own entries, never the consensus; entries and consensus rows are
  under the same row-level security as decisions.
- **"Final" exports are what an analysis uses**: the consensus where there is one, else the
  only submitted extraction; a study extracted twice and not reconciled is left out rather
  than guessed. "All" gives every extractor and the consensus, labelled, for checking.
- **The builder's column names come from labels** (`Participants (n)` → `participants_n`)
  and can be changed; they are the exports' column headings, so they follow the rules R
  and Stata accept.
- **Drag and drop, with buttons.** Fields reorder by dragging, and by "Move up" and "Move
  down" for keyboards and screen readers.

### Taken over from Codex
- The owner reassigned Codex's queue items 5–7 (extraction rules, citation writers, the
  methods text) to Claude Code on 2026-09-25 because Codex was busy. They follow the
  specifications in `AGENTS.md`, which now says so.

## Phase 9 — Polish, hardening, launch

### Command palette (guide 11.2)
- **Ctrl+K or ⌘K anywhere, and a "Search or jump to…" button in the top bar** for mouse,
  touch and anyone who does not know the shortcut. It never clashes with screening's
  single-key shortcuts, which take no modifier.
- **Built on Radix's dialog with the WAI-ARIA combobox pattern** (focus stays in the input,
  the active result is `aria-activedescendant`, results are grouped options), rather
  than a new dependency: the pieces were already in the bundle.
- **Pages, actions and reviews are filtered in the browser; records are searched on the
  server** with the records table's own search, from three characters, so a DOI, a PubMed
  id or title words all work, and blind mode applies as it does in the table. Only the
  current review is searched.
- **Only what the person may do is offered**: pages and actions follow the same
  permissions as the sidebar.
- **A record opens in the records table** (`?record=`), where its details already live.

### Notifications (guide 8.17)
- **Four kinds, as the guide lists them.** A new conflict tells those who may resolve it
  (owners, admins and trusted reviewers), never the person whose decision made it. An
  invitation tells an invitee who already has an account. "@Name" in a team note tells
  that member. An import finished or failed tells whoever started it.
- **Conflicts are counted, not repeated**: one unread notice per person and review ("3 new
  conflicts"), counting up until it is read, so a busy morning is one line, not fifty.
- **Written in the same transaction as what they announce**, so there is never a notice
  about something that did not happen.
- **Nothing blind mode hides.** A conflict notice says that disagreements exist, which
  only resolvers are told; a mention comes from a team note everyone can read anyway; a
  private note tells nobody.
- **Leaving a review hides its notices.** An invitation is about no review (the invitee
  cannot open it yet), so it carries the review's name, not its id, and does not link
  there: the invitation email has the link, and the token never enters the notice.
- **Mentions match a member's name after "@"**, ignoring case, not an @handle: Winnow has
  no handles, and names are what people see.
- **The bell asks for the unread count every minute and when the tab comes back**, rather
  than holding a connection per person; notices are not urgent to the second.
- **The daily digest is off by default** (guide 8.17), set per person under Account, sent
  once a morning (06:05 UTC) with what is still unread from the last day, and nothing on
  quiet days.
- **The menu is not modal**: a modal menu hides the page from screen readers while its
  links can still take focus, which axe reports as serious.

### Presence (guide 8.17)
- **Who and which stage, never which record or what was decided**, so blind mode loses
  nothing: "Grace is screening titles and abstracts".
- **A heartbeat every 30 seconds from an open, visible screening page**, held in Redis for
  a minute; a hidden tab goes quiet and a closed page says so at once. Nothing is stored
  in the database: presence is only ever "now".
- **Only people who screen announce themselves**; every member sees who is screening, on
  the review's overview and on the screening pages. Nobody is shown to themselves.

### Admin panel (guide 8.18)
- **Anyone who is not an instance administrator gets 404** from `/api/v1/admin/…`, as
  non-members get for a review: the panel is not advertised.
- **Disabling keeps everything**: the account cannot sign in and its sessions end at once,
  but its reviews, decisions and history stay. "This account is disabled" is said only
  after the right password (a wrong one is a wrong password, as for anyone), so it does
  not reveal which addresses have accounts. An administrator cannot disable themselves,
  so someone is always left to enable accounts.
- **Resetting two-factor is for a lost authenticator and lost recovery codes**: it turns
  two-factor off, ends the person's sessions and emails them; the panel asks the
  administrator to check who is asking first.
- **Only two settings change while Winnow runs: the registration mode and the Unpaywall
  email.** They are safe to change live and useful to (closing registration after a
  workshop). Everything else (email server, storage, AI provider, sizes) stays in `.env`,
  read at start-up, and is shown read-only; secrets are never shown, only whether they
  are set. A value set in the panel wins over `.env` until "Use the value in .env" clears
  it.
- **Health is read, never guessed**: the worker is alive if its arq health check is fresh
  (with its job counts), the queue length is the arq queue's, the disk is where files are
  kept, the database size is PostgreSQL's own, and the last backup is what `make backup`
  records (item 11), or "none recorded".

### Languages (guide 14)
- **Set up, and the shell moved, not every page at once.** i18next and a typed English
  catalogue are in place; the sidebar, top bar, command palette, notifications, menus,
  banners and error pages speak from it. Pages move to their own namespace when each is
  next changed (docs/i18n.md), which keeps this change reviewable and every page's tests
  unchanged.
- **The browser's language, no switcher yet**: a menu with one language would be noise.
  The first of the browser's preferred languages Winnow speaks wins, else English, and
  `<html lang>` follows it.
- **English is bundled; other languages will load when chosen.** i18next and
  react-i18next add 22.5 KB to the initial bundle (178.4 KB of the 200 KB budget);
  bundling further catalogues would eat the rest.
