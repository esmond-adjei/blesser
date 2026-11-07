# Blesser command map; `make help` lists targets. The backend runs through uv,
# the web app through npm (Node 26). Recipes assume Postgres from `make db`.

UV := uv run
API := cd api && $(UV)
WEB := npm --prefix webapp run
COMPOSE := docker compose

# Scratch test database (conftest.py default; override to match local Postgres).
TEST_DATABASE_URL ?= postgresql+asyncpg://blesser:blesser@localhost:5432/blesser_test

.PHONY: help install db db-down api worker web up up-backend migrate revision lint format typecheck test \
	test-web backup backup-verify vapid-keys build verify clean

help: ## List targets with one-line descriptions.
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

install: ## Install backend and web app dependencies.
	cd api && uv sync
	cd webapp && npm install

db: ## Start Postgres (required before api, worker, test, migrate).
	$(COMPOSE) up -d db

db-down: ## Stop Postgres without deleting its volume.
	$(COMPOSE) stop db

api: db ## Run the API with reload (localhost:8000).
	$(API) uvicorn api.main:app --reload --timeout-graceful-shutdown 3

worker: db ## Run the agent worker (pass flags: make worker ARGS="--concurrency 2").
	$(API) python -m api.worker $(ARGS)

web: ## Run the web app dev server (proxies /api to localhost:8000).
	$(WEB) dev

up: ## Full stack in Docker (web app :8080, api :8000).
	$(COMPOSE) up -d --build db api worker webapp

up-backend: ## Backend stack only in Docker (db, api, worker).
	$(COMPOSE) up -d --build db api worker

migrate: db ## Apply pending Alembic migrations (the API also does this on boot).
	$(API) alembic upgrade head

revision: db ## Draft a migration from model changes (make revision MSG="add a column").
	@test -n "$(MSG)" || (echo "MSG is required" && exit 1)
	$(API) alembic revision --autogenerate -m "$(MSG)"

lint: ## Ruff and oxlint. Must pass.
	$(API) ruff check .
	$(WEB) lint

format: ## Apply ruff format to the backend.
	$(API) ruff format .

typecheck: ## Pyright. Not a gate: the model providers carry known errors.
	$(API) uvx pyright@1.1.414

test: db ## Backend suite on a scratch database (make test T=tests/test_opportunities.py).
	@cd api && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 TEST_DATABASE_URL="$(TEST_DATABASE_URL)" $(UV) pytest -q $(T)

test-web: ## Web app unit tests.
	$(WEB) test

backup: ## Dump Postgres to ./backups (BACKUP_DIR, KEEP_DAYS, OFFSITE; see docs/backups.md).
	ops/backup.sh

backup-verify: ## Restore the newest dump into a scratch DB and check it, then drop it.
	ops/restore-verify.sh

vapid-keys: ## Print a VAPID key pair for browser push (docs/notifications.md).
	@cd api && $(UV) python -m scripts.vapid_keys

build: ## Type-checked production build of the web app.
	$(WEB) build

verify: lint test test-web build ## All gates in one command.
	@echo "verify: lint, tests and build all passed"

clean: ## Remove build output and caches (never touches Postgres volumes).
	rm -rf webapp/dist webapp/.vite
	find api webapp/src -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf api/.pytest_cache api/.ruff_cache webapp/node_modules/.vite
