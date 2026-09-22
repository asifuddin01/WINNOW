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
  uses pure white or pure black. Light is a matte, low-glare warm paper (`#EEEAE5`) with
  charcoal text (`#2A2520`) at 12.7:1 instead of 20:1; cards sit barely above the page so
  nothing glows (a brighter `#F9F6F2` paper still felt like too much light). Dark is "night slate", a soft blue-grey
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
