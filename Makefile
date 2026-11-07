# Graduator command map. Every recipe mirrors the README; `make help` lists targets.
# Backend runs through uv, the webapp through npm. Recipes assume Postgres
# from `make db` wherever a database is involved.

UV := uv run
API := cd api && $(UV)
WEB := npm --prefix webapp run
SITE := npm --prefix website run
COMPOSE := docker compose

# Scratch test database (conftest.py default; override to match local Postgres).
TEST_DATABASE_URL ?= postgresql+asyncpg://graduator:graduator@localhost:5432/graduator_test

.PHONY: help install db db-down tools api worker web site site-build site-preview site-assets design-system up up-backend \
	migrate history revision lint format typecheck test remove-professor backup backup-verify usage-report encrypt-secrets vapid-keys build verify clean

help: ## List targets with one-line descriptions.
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

install: ## Install backend and frontend dependencies.
	cd api && uv sync
	cd webapp && npm install
	cd website && npm install

db: ## Start Postgres (required before api, worker, test, migrate).
	$(COMPOSE) up -d db

db-down: ## Stop Postgres without deleting its volume.
	$(COMPOSE) stop db

tools: ## Start pgAdmin for the database (localhost:5050).
	$(COMPOSE) --profile tools up -d pgadmin

api: db ## Run the API with reload (localhost:8000).
	$(API) uvicorn api.main:app --reload --timeout-graceful-shutdown 3

worker: db ## Run the agent worker (pass flags: make worker ARGS="--concurrency 5").
	$(API) python -m api.worker $(ARGS)

web: ## Run the webapp dev server (proxies /api to localhost:8000).
	$(WEB) dev

site: ## Run the marketing site dev server (localhost:4321).
	$(SITE) dev

site-build: ## Build the marketing site into website/dist.
	$(SITE) build

site-assets: ## Regenerate the site's logo, favicon and social card from the app's assets.
	node website/scripts/build-logo.mjs
	node website/scripts/build-favicon.mjs
	node website/scripts/build-og.mjs

site-preview: ## Serve the built marketing site (localhost:4321).
	$(SITE) preview

design-system: ## Copy docs/design-system (tokens, components, fonts) into the webapp and site.
	node docs/design-system/sync.mjs

up: ## Full stack in Docker (webapp :8080, api :8000).
	$(COMPOSE) up -d --build db api worker webapp

up-backend: ## Backend stack only in Docker (db, api, worker).
	$(COMPOSE) up -d --build db api worker

migrate: db ## Apply pending Alembic migrations.
	$(API) alembic upgrade head

history: ## Show applied and pending migrations.
	$(API) alembic history

revision: db ## Draft a migration from model changes (make revision MSG="add lab_name").
	@test -n "$(MSG)" || (echo "MSG is required" && exit 1)
	$(API) alembic revision --autogenerate -m "$(MSG)"

lint: ## Ruff check and oxlint. Must pass.
	$(API) ruff check .
	$(WEB) lint

format: ## Apply ruff format to the backend tree.
	$(API) ruff format .
# Note: `ruff format --check .` is not a gate yet — 30 files predate
# adoption and reformatting them all at once would bury real diffs.
# New files must still land formatted (checked in review).

typecheck: ## Pyright. Not a gate: the providers and the tests carry pre-existing errors.
	$(API) uvx pyright@1.1.414

test: db ## Backend suite on the scratch database (make test T=tests/test_crud.py).
	@cd api && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 TEST_DATABASE_URL="$(TEST_DATABASE_URL)" $(UV) pytest -q $(T)

backfill-owner: db ## Assign every unowned row to one account (EMAIL=you@example.com). Run after 015, before 016.
	@test -n "$(EMAIL)" || (echo "EMAIL is required" && exit 1)
	@cd api && $(UV) python -m scripts.backfill_owner --email "$(EMAIL)"

remove-professor: db ## Remove a researched person everywhere + opt them out (ARGS='--name "Ada" --school "ETH"').
	@test -n "$(ARGS)" || (echo "ARGS is required" && exit 1)
	@cd api && $(UV) python -m scripts.remove_professor $(ARGS)

backup: ## Dump Postgres to ./backups (BACKUP_DIR, KEEP_DAYS, OFFSITE; see docs/backups.md).
	ops/backup.sh

backup-verify: ## Restore the newest dump into a scratch DB and check it, then drop it.
	ops/restore-verify.sh

usage-report: db ## Ops: model calls/tokens across accounts (DAYS=30).
	@cd api && $(UV) python -m scripts.usage_report --days $(or $(DAYS),30)

encrypt-secrets: db ## Encrypt stored provider API keys at rest (one-off, idempotent).
	@cd api && $(UV) python -m scripts.encrypt_secrets

vapid-keys: ## Print a VAPID key pair for browser push (docs/notifications.md).
	@cd api && $(UV) python -m scripts.vapid_keys

build: ## Type-checked production build of the webapp.
	$(WEB) build

verify: lint test build site-build ## All green gates in one command.
	@echo "verify: lint, test, and build all passed"

clean: ## Remove build output and caches (never touches Postgres volumes).
	rm -rf webapp/dist webapp/.vite website/dist website/.astro
	find api webapp/src -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf api/.pytest_cache api/.ruff_cache webapp/node_modules/.vite
