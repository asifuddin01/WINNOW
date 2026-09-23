# Winnow

*Separate the evidence from the noise.*

Winnow is a free, open, self-hostable platform for systematic, scoping and rapid reviews:
import → deduplicate → screen → resolve → full text → extract → appraise → report (PRISMA 2020).

> **Status:** Phase 4 (deduplication). Accounts and the security core, reviews with their
> team and setup, importing up to 20 search exports at once, the records table, and finding
> and merging duplicates across databases are in place; screening arrives in Phase 5. See [CHANGELOG.md](CHANGELOG.md) and the
> build plan in [WINNOW_BUILD_GUIDE.md](WINNOW_BUILD_GUIDE.md), Section 17.

## Run it

You need **Docker** (with Compose v2) and **make**. On Windows, use WSL2.

```bash
make dev
```

Then open <http://localhost:8080> (use that address, not 127.0.0.1: writes are accepted
only from the configured origin) and create an account. Emails, such as the confirmation
link, land in Mailpit at <http://localhost:8025>. The first run builds the images, which
takes a few minutes. `make dev` creates `.env` from `.env.example` with fresh random keys if
you do not have one yet.

Running Winnow for yourself only? Set `WINNOW_SINGLE_USER=true` in `.env`: the first visit
creates your administrator account, with no email step. For servers, create administrators
with `make create-admin email=you@example.org name="Your Name"`. To look around with
something already set up, `make seed email=you@example.org` adds a worked example review.

| Command | What it does |
|---|---|
| `make dev` | Start everything in the foreground: Caddy, API, worker, web, Postgres, Redis |
| `make up` / `make down` | Start in the background (waits until healthy) / stop |
| `make migrate` | Apply database migrations |
| `make create-admin email=… name="…"` | Create a verified administrator (asks for the password) |
| `make seed email=…` | Put a worked example review in that account |
| `make revision m="…"` | Autogenerate a migration from model changes |
| `make test` | Backend (pytest) and frontend (Vitest) tests, with coverage |
| `make lint` / `make typecheck` | ruff + ESLint + formatting / mypy `--strict` + tsc |
| `make check` | Everything CI runs except end-to-end |
| `make e2e` | Playwright against the running stack (needs Node 22+ on the host) |
| `make api-types` | Regenerate the frontend's API types after changing the API |
| `make size` | Production build plus the initial-bundle budget (200 KB gzipped) |
| `make help` | Every target |

Everything except `make e2e` runs inside the containers, so a fresh clone needs nothing else.
For editor support you can also install the dependencies locally: `uv sync` in `backend/`,
`pnpm install` in `frontend/`.

## Sign in with Google (optional)

The "Continue with Google" button appears once Winnow has Google credentials:

1. In [Google Cloud Console](https://console.cloud.google.com/apis/credentials), set up the
   OAuth consent screen (app name "Winnow"; the scopes are `openid`, `email` and `profile`,
   which need no Google review), then create an **OAuth client ID** of type
   **Web application**.
2. Add the authorized redirect URI `http://localhost:8080/api/v1/auth/google/callback`
   (for a server: `https://your-domain/api/v1/auth/google/callback`).
3. Put the client ID and secret in `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`,
   then run `make up`.

A Google sign-in joins the Winnow account with the same verified email, or creates one if
registration is open. Accounts with two-factor authentication still ask for their code.

## What runs where

| Service | Role |
|---|---|
| `caddy` | The only published port (`127.0.0.1:8080`). Routes `/api/*` to the API and everything else to the web app |
| `api` | FastAPI on Python 3.12. Docs at <http://localhost:8080/api/docs> in development |
| `worker` | ARQ background jobs (imports, dedup, ranking, exports in later phases) |
| `web` | React 19 + Vite dev server with hot reload |
| `db` / `redis` | PostgreSQL 16 and Redis 7, reachable only on the internal network |
| `mailpit` | Catches every email in development: <http://localhost:8025> |

Health: `GET /api/v1/healthz` (process is up) and `GET /api/v1/readyz` (database and Redis reachable).

## Repository layout

```
backend/    FastAPI app (app/), Alembic migrations, tests (unit/, integration/, security/)
frontend/   React + TypeScript + Tailwind + shadcn/ui, TanStack Router and Query
e2e/        Playwright tests
docs/       decisions.md and, later, user, admin and security guides
```

Project conventions live in [CLAUDE.md](CLAUDE.md); design decisions and their reasons in
[docs/decisions.md](docs/decisions.md).

## License

[AGPL-3.0](LICENSE). Anyone running a modified public version must share their changes.

Built by [Asif](https://asifuddin.com).
