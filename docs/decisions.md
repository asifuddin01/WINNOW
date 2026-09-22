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
