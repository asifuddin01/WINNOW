# Winnow developer commands. Everything except `e2e` runs inside Docker, so a fresh
# clone needs only Docker and make. `make help` lists the targets.

COMPOSE ?= docker compose
# The full stack scans uploads with ClamAV; `make local` leaves it out (guide 16.2).
SCAN := --profile scan
# The web container keeps the image's node_modules in an anonymous volume. Removing the
# container with that volume before each start refreshes node_modules after a dependency
# change; --renew-anon-volumes did the same but left every old volume behind (~200 MB each).
FRESH_WEB = $(COMPOSE) rm --force --stop --volumes web
# The pnpm pinned in e2e/package.json, run through npx (works without corepack).
PNPM ?= npx --yes $(shell node -p "require('./e2e/package.json').packageManager" 2>/dev/null || echo pnpm)
API := $(COMPOSE) run --rm api
API_NO_DEPS := $(COMPOSE) run --rm --no-deps api
WEB := $(COMPOSE) run --rm --no-deps web

.DEFAULT_GOAL := help
.PHONY: help env dev up local down logs ps build migrate revision seed seed-large \
	test test-backend test-frontend e2e lint typecheck format check api-types size clean create-admin

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
	$(FRESH_WEB)
	$(COMPOSE) $(SCAN) up --build

up: .env ## Start the stack in the background and wait until it is healthy
	$(FRESH_WEB)
	$(COMPOSE) $(SCAN) up --build --detach --wait
	@echo "Winnow is running at http://localhost:$${WINNOW_PORT:-8080}"

local: .env ## Lightweight stack without ClamAV, for low-memory laptops: uploads stay unscanned
	@echo "Starting without ClamAV: uploaded PDFs will not be scanned for viruses."
	$(FRESH_WEB)
	CLAMAV_HOST= $(COMPOSE) up --build --detach --wait
	@echo "Winnow is running at http://localhost:$${WINNOW_PORT:-8080} (no virus scanning)"

down: ## Stop the stack (data volumes are kept)
	$(COMPOSE) $(SCAN) down

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

create-admin: .env ## Create a verified instance administrator: make create-admin email=… name="…"
	@test -n "$(email)" -a -n "$(name)" || (echo 'Usage: make create-admin email=you@example.org name="Your Name"' && exit 1)
	$(API) python -m app.cli create-admin --email "$(email)" --name "$(name)"

seed: .env ## Demo review in an existing account: make seed email=you@example.org
	@test -n "$(email)" || (echo 'Usage: make seed email=you@example.org' && exit 1)
	$(API) python -m app.cli seed --email "$(email)"

seed-large: .env ## 100,000 generated records for the budgets: make seed-large email=you@example.org
	@test -n "$(email)" || (echo 'Usage: make seed-large email=you@example.org [records=100000]' && exit 1)
	$(API) python -m app.cli seed-large --email "$(email)" --records "$(or $(records),100000)"

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
	$(COMPOSE) $(SCAN) down --volumes --remove-orphans
