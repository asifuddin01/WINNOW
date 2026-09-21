# Winnow developer commands. Everything except `e2e` runs inside Docker, so a fresh
# clone needs only Docker and make. `make help` lists the targets.

COMPOSE ?= docker compose
# The pnpm pinned in e2e/package.json, run through npx (works without corepack).
PNPM ?= npx --yes $(shell node -p "require('./e2e/package.json').packageManager" 2>/dev/null || echo pnpm)
API := $(COMPOSE) run --rm api
API_NO_DEPS := $(COMPOSE) run --rm --no-deps api
WEB := $(COMPOSE) run --rm --no-deps web

.DEFAULT_GOAL := help
.PHONY: help env dev up down logs ps build migrate revision seed seed-large \
	test test-backend test-frontend e2e lint typecheck format check api-types size clean

help: ## List the targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-z0-9-]+:.*## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

env: .env ## Create .env from .env.example with fresh random keys (never overwrites)

.env:
	@cp .env.example .env
	@secret=$$(openssl rand -hex 32); key=$$(openssl rand -base64 32); \
		sed -i.bak -e "s|^SECRET_KEY=.*|SECRET_KEY=$$secret|" \
			-e "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=$$key|" .env && rm -f .env.bak
	@echo "Created .env with a random SECRET_KEY and ENCRYPTION_KEY."

dev: .env ## Start the whole stack in the foreground (http://localhost:8080)
	$(COMPOSE) up --build --renew-anon-volumes

up: .env ## Start the stack in the background and wait until it is healthy
	$(COMPOSE) up --build --renew-anon-volumes --detach --wait
	@echo "Winnow is running at http://localhost:$${WINNOW_PORT:-8080}"

down: ## Stop the stack (data volumes are kept)
	$(COMPOSE) down

logs: ## Follow logs from every service
	$(COMPOSE) logs --follow

ps: ## Show service status and health
	$(COMPOSE) ps

build: .env ## Build the development images
	$(COMPOSE) build

migrate: .env ## Apply database migrations (alembic upgrade head)
	$(API) alembic upgrade head

revision: .env ## Create a migration from model changes: make revision m="add users"
	@test -n "$(m)" || (echo 'Usage: make revision m="describe the change"' && exit 1)
	$(API) alembic revision --autogenerate -m "$(m)"

seed: ## Demo project with 500 records and 2 users (arrives with Phases 2-3)
	@echo "Nothing to seed yet: demo data needs projects (Phase 2) and records (Phase 3)."

seed-large: ## 100,000-record project for performance budgets (arrives with Phase 3)
	@echo "Nothing to seed yet: the large seed arrives with records (Phase 3)."

test: test-backend test-frontend ## Run backend and frontend tests

test-backend: .env ## pytest against a separate test database, with coverage
	$(API) pytest --cov --cov-report=term-missing

test-frontend: .env ## Vitest with coverage
	$(WEB) pnpm test --coverage

e2e: ## Playwright against the running stack (make up first); needs Node 22+ on the host
	cd e2e && $(PNPM) install --frozen-lockfile && $(PNPM) exec playwright install chromium \
		&& $(PNPM) exec playwright test

lint: .env ## ruff, ESLint and format checks
	$(API_NO_DEPS) sh -c "ruff check . && ruff format --check ."
	$(WEB) sh -c "pnpm lint && pnpm format:check"

typecheck: .env ## mypy --strict and tsc
	$(API_NO_DEPS) mypy
	$(WEB) pnpm typecheck

format: .env ## Apply ruff and Prettier formatting
	$(API_NO_DEPS) sh -c "ruff check --fix . && ruff format ."
	$(WEB) pnpm format

check: lint typecheck test ## Everything CI checks, except e2e

api-types: .env ## Regenerate frontend API types from the OpenAPI schema
	$(COMPOSE) run --rm --no-deps -T api python -m app.openapi > frontend/src/api/openapi.json
	$(WEB) pnpm api-types

size: .env ## Production build plus the initial-bundle budget check
	$(WEB) sh -c "pnpm build && pnpm size"

clean: ## Stop the stack and delete its data volumes
	$(COMPOSE) down --volumes --remove-orphans
