# Winnow

*Separate the evidence from the noise.*

Winnow is a free, open, self-hostable platform for systematic, scoping and rapid reviews:
import → deduplicate → screen → resolve → full text → extract → appraise → report (PRISMA 2020).

> **Status:** Phase 0 (foundation). The stack, app shell, health checks and CI are in place;
> accounts arrive in Phase 1 and reviews in Phase 2. See [CHANGELOG.md](CHANGELOG.md) and the
> build plan in [WINNOW_BUILD_GUIDE.md](WINNOW_BUILD_GUIDE.md), Section 17.

## Run it

You need **Docker** (with Compose v2) and **make**. On Windows, use WSL2.

```bash
make dev
```

Then open <http://localhost:8080>. The first run builds the images, which takes a few minutes.
`make dev` creates `.env` from `.env.example` with fresh random keys if you do not have one yet.

| Command | What it does |
|---|---|
| `make dev` | Start everything in the foreground: Caddy, API, worker, web, Postgres, Redis |
| `make up` / `make down` | Start in the background (waits until healthy) / stop |
| `make migrate` | Apply database migrations |
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

## What runs where

| Service | Role |
|---|---|
| `caddy` | The only published port (`127.0.0.1:8080`). Routes `/api/*` to the API and everything else to the web app |
| `api` | FastAPI on Python 3.12. Docs at <http://localhost:8080/api/docs> in development |
| `worker` | ARQ background jobs (imports, dedup, ranking, exports in later phases) |
| `web` | React 19 + Vite dev server with hot reload |
| `db` / `redis` | PostgreSQL 16 and Redis 7, reachable only on the internal network |

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
