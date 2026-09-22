# Changelog

All notable changes, one section per build phase (guide Section 17).

## Phase 0: Foundation (2026-09-21)

### Changed (2026-09-22)
- Softer colours for long screening sessions: a warm off-white "paper" light theme and a
  blue-grey "night slate" dark theme, with no pure white or pure black. Body text contrast
  went from 20:1 to 13:1 (light) and from 19:1 to 12.5:1 (dark), still above WCAG AAA.

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
- Content-Security-Policy and HSTS, CSRF, sessions and rate limits: Phase 1.
- Dependency and secret scanning in CI (pip-audit, pnpm audit, semgrep, gitleaks, Trivy):
  Phase 1, with the rest of the security work.
- ClamAV and MinIO services and `make local`: Phases 3 and 7, when uploads exist.
- Firefox and WebKit in Playwright: with the full user journey.
