# Changelog

All notable changes, one section per build phase (guide Section 17).

## Phase 5: Title and abstract screening, blind mode, conflicts (2026-09-23)

### Added
- A screening page that is ready before you are: the next ten records are loaded ahead,
  a decision moves on at once and is saved behind the screen, and a failed save puts the
  record back with the reason. Decisions made while offline wait and are sent when the
  connection returns.
- Three layouts: three panes on a desktop (history, record, decision), two on a tablet,
  a focus mode (F) with only the record, and on a phone a card that swipes right to
  include, left to exclude and up (from its handle) for maybe, with the three buttons
  fixed below it and reasons, labels and notes in a sheet. Works at 360 pixels.
- The keyboard shortcuts in guide 11.4: I, M, E (or 1, 2, 3) to decide; R, then a
  number, for a reason; L for labels; N for a note; J and K (or the arrows) to move;
  Ctrl/⌘+Z to undo; H for highlighting; F for focus; / to search; ? for the list. None
  of them fire while typing.
- Keyword highlighting from the review's keyword groups, in their colours, with a legend;
  plain terms are matched literally, patterns as patterns, accented letters count as
  letters, and a pattern that will not compile is skipped instead of breaking the page.
- Exclusion reasons (required when the review says so), labels, and notes (private or for
  the team) on each record; undo; and a history of your own decisions that reopens any of
  them to change.
- Time on each record is measured while the page is visible and added up across visits.
- Assignment: every reviewer screens every record, or records are shared out so each gets
  the review's number of reviewers, spread evenly and stable as the team changes.
- Record status follows guide 6.4 after every decision, undo, resolution, merge and change
  to the review's rules; an included title and abstract moves the record to full text.
- Blind mode enforced on the server: a blinded reviewer is sent no one else's decision,
  reason, note or label, not even whether they disagree. The records list, its counts and
  its filters show their own decisions. Owners and admins can see through it unless they
  choose to stay blind.
- A conflicts page for owners, admins and anyone given the right: both decisions side by
  side with reasons and notes, the abstract on demand, a filter for where two chosen
  reviewers disagree, resolve with a reason and a note, or ask the reviewers to discuss
  (a team note, and an email to them).
- Bulk decisions for admins: include or exclude every record matching a records-list
  search, after seeing how many it will be; if the records change before confirming,
  nothing is decided and the new count is shown.
- Merging duplicates now moves decisions, labels, notes and resolutions to the kept
  record, and recomputes both stages.
- Search terms `label:` and `type:` in the records list.
- Tests: status rules, split assignment, bulk decisions, conflicts, merge migration, a
  blind-mode security suite, and a Playwright journey with two reviewers — one on a
  desktop with the keyboard, one on a 360-pixel phone with the buttons — that ends in a
  resolved conflict.

### Measured
- 100,000 records, one project: next page of the queue p50 9 ms / p95 15 ms by relevance
  and 7 / 10 ms at random; saving a decision 9 / 13 ms; progress 63 / 131 ms.

## Phase 4: Deduplication (2026-09-23)

### Added
- The algorithm in guide 9.1 as a worker job: exact DOI and PubMed id matches, blocking,
  weighted pairwise scoring, union-find clusters, and the most complete record as primary.
  The pure engine is Codex's (`app/dedup`); the job, the tables and the screens are here.
- Duplicates are looked for as soon as an import finishes, and on demand with "Find
  duplicates". Groups Winnow is certain about — an exact identifier, or a score of 0.98 and
  above with no conflicting DOI — merge themselves; both are project settings.
- A review screen with the copies side by side, the fields they disagree about marked, the
  database each copy came from, and a comparison of abstracts. Actions: merge keeping the
  suggested copy, merge keeping another, not duplicates, and merge every certain group.
- Merging never deletes: the secondary keeps its row with `is_duplicate` and
  `duplicate_of`, leaves the screening list, and is counted for PRISMA. "Not duplicates"
  is remembered, so the same group is not proposed again.
- Upload up to 20 search exports at once. Each file becomes its own import (so PRISMA can
  count each search and any one can be undone), the database is guessed from each file
  name and can be corrected, and the search date and string are kept with every file.
  One unreadable file is reported beside the others instead of failing the upload.
- More sources to choose from: IEEE Xplore, ACM Digital Library, ProQuest, Google Scholar,
  Semantic Scholar, Dimensions, arXiv, bioRxiv, medRxiv, SSRN, ClinicalTrials.gov, WHO
  ICTRP and hand searching, alongside the bibliographic databases.
- Tests: the known-duplicates fixture through the whole database pipeline (precision and
  recall asserted), merging, choosing a different primary, not duplicates across reruns,
  auto-resolve, permissions, and Playwright journeys for a multi-file upload and for
  deduplicating two databases.

### Fixed
- The BibTeX reader treated a quotation mark inside a braced value as a delimiter, so one
  quote in an abstract swallowed every entry after it. A real arXiv export lost 122 of its
  272 records this way; all of them now come in.

- Running a whole review folder through it (38 files, 8,298 records) found four problems,
  all fixed: every finished import queued its own dedup run, so a drop of files started
  dozens at once on one review; the trigram join ran past a minute at that size; groups
  that needed a person were padded with identical copies from overlapping queries; and a
  live event stream kept the API from ever finishing a reload or shutdown. Now one dedup
  run per review is queued (debounced, and it goes round again if records arrive while it
  works); the trigram join runs only for small reviews and under a statement timeout;
  identical copies inside an uncertain group are merged first; and event streams end
  after five minutes and reconnect, with uvicorn given a graceful-shutdown timeout.
- The side-by-side comparison ignores case and punctuation when marking differences, so
  the year and journal that really differ are not lost among titles written in capitals.

### Measured
- 50,000 records: 10.5 s, database writes included (budget 30 s).
- A real multi-query arXiv search, 637 records of 459 papers: precision 98.97 %, recall
  100 % against the search's own provenance.
- A real scoping-review folder — IEEE Xplore, Scopus, PubMed and arXiv, 8,298 records in
  38 files: one run of about 10 s, 2,476 duplicates merged without asking, 72 groups left
  for a person, each of two or three records (mostly a preprint against its published
  version).

## Phase 3: Import and records (2026-09-23)

### Added
- Storage behind one small interface: files land on disk under `UPLOAD_DIR` today, and S3
  can slot in later without touching the import.
- Readers for the six export formats in guide 8.1 — RIS, BibTeX, PubMed NBIB (MEDLINE),
  PubMed XML, EndNote XML and CSV/TSV with a column mapping — each choosing itself from the
  file's own content, not its extension.
- Normalisation on the way in: titles folded for comparison, DOIs lowercased and stripped of
  their prefix, authors split into `Family, Given`, years pulled out of dates, abstracts
  cleaned of structured-abstract noise, and lists capped.
- Upload, preview and confirm: nothing enters the review until the first records Winnow read
  are on screen, with the CSV mapping it guessed from the headings, ready to correct.
- The import itself runs in the worker and writes with PostgreSQL `COPY`, so 10,000 records
  take about two seconds and 100,000 about 36. Progress arrives over a server-sent event
  stream (`GET /projects/{id}/events`) that also catches up a page opened mid-import.
- Records that cannot be read are reported with their line or entry number and the reason,
  and the rest still come in. Import history lists every file, what came in and what did not,
  with an undo that removes exactly what that file brought.
- Records: a virtualised table that scrolls 100,000 rows, keyset pagination in six orders, a
  detail panel, and filters with counts from a cached facets endpoint.
- Full-text search from guide 8.9 — `"exact phrase"`, `-exclude`, `author:`, `journal:`,
  `year:2018..2024`, and a DOI or PubMed id pasted straight in — over a generated tsvector
  with GIN indexes, plus trigram indexes for title and author matching.
- Parser fixtures for the databases in guide 15 (Ovid Embase, PubMed, Scopus, Web of
  Science, CINAHL, Cochrane, Zotero, EndNote) and a deliberately messy file: BOM, CRLF,
  HTML entities, accents and a record with no end marker.
- Tests: the readers against those real exports, an end-to-end import through the worker, the
  search syntax, and a Playwright journey from upload to a searchable record.

### Changed
- `records.doi` is text rather than `citext` — binary `COPY` has no encoder for `citext`, and
  lookups use the normalised `doi_norm` column anyway.

## Phase 2: Reviews, team and settings (2026-09-23)

### Added
- Reviews (projects): create with a three-step wizard, edit, archive, hand on to another
  member, delete with a typed confirmation, and copy a whole setup into a new review.
- Roles from guide 7 — owner, admin, reviewer, viewer — behind one central check,
  `require_project_role`, on every project route. Non-members get the same 404 as for a
  review that does not exist, so nobody can learn what exists.
- Members and invitations: invite by email, withdraw, change roles, remove, leave. An
  invitation works once, for a week, and only for someone signed in with the invited,
  confirmed address; instances that send no email can pass the link on by hand. On
  invite-only instances, the invitation is also the way to register.
- Setup for each review: inclusion and exclusion criteria (ordered), keyword groups with
  colours and terms, exclusion reasons prefilled with the nine from guide 8.2, and labels.
- Keyword patterns are limited to a subset that means the same in JavaScript and Python and
  cannot backtrack for ever (no lookarounds, backreferences or repeated repeats).
- Project settings from guide 6.2 — blind mode, reviewers per record, what a “maybe”
  counts as, when a reason is required, ranking, AI assist, the stopping rule, assignment
  and keyword highlighting — plus a personal “keep me blind too” for owners and admins.
- My reviews dashboard, a review overview with a setup checklist, and a review sidebar.
- The audit log now records every project, member, invitation and setup change, and blind
  mode toggles on their own.
- `make seed email=you@example.org` puts a worked example review in an account.
- Tests: the guide's non-member check across every project route, the role matrix, IDOR
  attempts with ids from another review, invitation security, the pattern subset, and a
  Playwright journey where two people set up and share a review.

### Changed
- Registration accepts an invitation token, and `/auth/options` reports whether the
  instance has an AI provider and whether owners must use two-factor authentication.

## Phase 1: Accounts and security (2026-09-22)

### Added
- Accounts: register, confirm email, sign in, sign out, sign out everywhere, forgotten and
  changed passwords, and a first-run setup page for single-user mode. `make create-admin`.
- Argon2id password hashing (64 MiB, 3 passes), rehashed on sign-in when parameters change;
  12-character minimum and a k-anonymity breach check.
- Redis sessions in `__Host-` cookies (HttpOnly, Secure, SameSite=Lax), 7-day idle and
  30-day absolute expiry, a new id on every sign-in and privilege change, a device list with
  per-device sign-out.
- CSRF protection on every write: a signed token bound to the session plus an Origin check.
- TOTP two-factor authentication with QR setup, encrypted secrets, replay protection and ten
  single-use recovery codes that can be regenerated.
- Rate limits (sign-in, registration, password reset, verification, general API) with
  `Retry-After`, and a 15-minute lock after 10 failed sign-ins, emailed to the owner.
- Append-only audit log (a trigger rejects UPDATE, DELETE and TRUNCATE) recording every
  sign-in, failure, lock, registration, verification, password and 2FA change.
- Security headers in Caddy: the Content-Security-Policy from guide 12.5, HSTS over HTTPS,
  and a deny-all policy for API responses.
- Email through the worker (SMTP with STARTTLS or TLS); Mailpit catches it in development.
- Sign-in, registration, confirmation, password reset and setup pages; an account page for
  the password, two-factor and devices; a user menu; a "confirm your email" banner.
- Sign in with Google (OpenID Connect with PKCE, state and nonce), linking to the account
  with the same verified email or creating one; two-factor still applies. Off until
  `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set.
- CI: gitleaks, pip-audit, pnpm audit, semgrep and Trivy; Dependabot.
- Tests: security suite from guide 12.10 (fixation, CSRF, lockout, rate limits, sign-in
  required on every private route, 2FA replay, append-only audit, no secrets in logs), the
  frontend auth flows, and a Playwright journey from registration through 2FA and reset.

## Phase 0: Foundation (2026-09-21)

### Changed (2026-09-22)
- Softer colours for long screening sessions: a matte, low-glare soft grey-white paper light theme and
  a blue-grey "night slate" dark theme, with no pure white or pure black. Body text contrast
  went from 20:1 to 14.5:1 (light) and from 19:1 to 14:1 (dark), still above WCAG AAA. Dark-mode text is a touch
  heavier (weight 430) so it stays crisp.

### Added
- Repository structure from guide Section 5, AGPL-3.0 license, README, `docs/decisions.md`.
- Docker Compose development stack: PostgreSQL 16, Redis 7, a one-shot `migrate` job, API
  with reload, ARQ worker, Vite dev server and Caddy on `127.0.0.1:8080`, each with a
  healthcheck. Database and Redis are not published to the host.
- FastAPI app factory configured entirely from the environment (pydantic-settings). Startup
  fails on a placeholder or short `SECRET_KEY`, or an `ENCRYPTION_KEY` that is not 32 bytes of
  base64. `make env` writes a `.env` with random keys and never overwrites one.
- `GET /api/v1/healthz` and `GET /api/v1/readyz` (checks PostgreSQL and Redis; 503 names what
  failed).
- RFC 9457 problem details for every error, also described that way in the OpenAPI document,
  so the generated frontend types know the error shape. Validation errors never echo the
  submitted value.
- Request ids on every response and log line; structured JSON logs in production. Access logs
  record the route template, never the raw path, so tokens in URLs stay out of logs. API
  responses default to `Cache-Control: no-store`.
- Alembic with an async environment and a first migration enabling `citext`, `pg_trgm` and
  `pgcrypto` (guide 6.3). Tests check upgrade, downgrade and that models match migrations.
- ARQ worker with a `ping` job and a Redis round-trip test.
- React 19, TypeScript (strict), Vite 8, Tailwind CSS 4, shadcn/ui on Radix, TanStack Router
  (file routes, per-route code splitting, preload on intent) and TanStack Query.
- App shell: collapsible sidebar (icons only when collapsed, a sheet on phones), top bar with
  breadcrumbs and a light / dark / system theme menu, skip-to-content link, a status banner
  shown only when offline or when the server is not ready, and the global footer
  "Winnow · Built by Asif" on every page, including not-found and error pages.
- Design tokens: teal `#0F766E` accent, slate neutrals, include/exclude/maybe/conflict colours,
  self-hosted Inter.
- Typed API client generated from OpenAPI (`make api-types`), with `ApiError` carrying the
  server's request id.
- Tests: 43 backend (97% coverage, 90% enforced), 23 frontend (95% line coverage, thresholds
  enforced), 18 Playwright tests on desktop and phone viewports including axe accessibility
  checks in light and dark.
- CI (GitHub Actions): ruff, mypy `--strict`, pytest with PostgreSQL and Redis; ESLint,
  Prettier, tsc, Vitest, production build with a 200 KB initial-bundle budget; generated API
  types must be current; end-to-end on the real Compose stack; production image builds.
- Makefile targets: `dev`, `up`, `down`, `logs`, `migrate`, `revision`, `test`, `lint`,
  `typecheck`, `format`, `check`, `e2e`, `api-types`, `size`, `clean`, plus `seed` and
  `seed-large` placeholders until records exist.

### Not yet (planned)
- ClamAV and MinIO services and `make local`: Phases 3 and 7, when uploads exist.
- Firefox and WebKit in Playwright: with the full user journey.
