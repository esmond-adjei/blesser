# Graduator API

The FastAPI backend and agent worker. One Docker image runs both; the start command decides which one.

## Run it

Start Postgres first (`make db` from the repo root), then:

```bash
uv sync --group dev
cp .env.example .env                   # add your model key

uv run uvicorn api.main:app --reload --timeout-graceful-shutdown 3   # API on http://localhost:8000
uv run python -m api.worker            # agent worker, in a second terminal
```

Migrations run automatically when the API starts. Interactive API docs are served at http://localhost:8000/docs.

## Configuration

Every setting, with its default, is in [`.env.example`](.env.example). The ones you need:

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY` | The agent's model: `anthropic`, `openai`, `gemini`, `ollama` or `openai-compatible`. Accounts can override this in Settings → Models. |
| `TAVILY_API_KEY`, `BRAVE_API_KEY` | Web search for finding programmes and faculty. Tried in the order set by `SEARCH_PROVIDERS`; keyless DuckDuckGo runs only when listed there. |
| `EMBEDDING_PROVIDER`, `EMBEDDING_API_KEY` | Fit scores. `local` uses keyword overlap and needs no key (for development only). |
| `DATABASE_URL` | Postgres. It's the only supported database. |
| `AUTH_SECRET` | Signs sign-in tokens. Required in production; if it's left empty, every restart signs everyone out. |
| `SECRETS_KEY` | Encrypts stored provider API keys. Defaults to a key derived from `AUTH_SECRET`; with neither set, keys are stored in plaintext. |
| `MAIL_BACKEND`, `MAIL_FROM`, `SMTP_*`, `APP_BASE_URL` | Password-reset and verification emails. `console` (the default) prints them to the API log; set `smtp` for real delivery ([docs/email.md](../docs/email.md)). |
| `OAUTH_GOOGLE_CLIENT_ID`, `OAUTH_GOOGLE_CLIENT_SECRET` | Google sign-in. The button is hidden until both are set. |
| `BILLING_ENFORCED` | `false` (default) keeps every account on Beta: all features, no limits. |

## Layout

```
api/
  main.py        app, /health, /ready, routers
  worker.py      worker entry point
  core/          config, database, rate limits
  agent/         tool-use loop, LLM providers, tool dispatch, quotas
  auth/          accounts, tokens, profile, email links, Google sign-in
  account/       data export
  billing/       plans and paywall checks
  metering/      daily usage rollups
  flows/         user-defined agent pipelines
  runs/          runs, task queue, live events, health
  prospects/     schools, programmes, professors, papers
  candidates/    scoring, verification, review
  outreach/      email drafts
  applications/  application tracker
  notifications/ inbox, browser push, email notifications, deadline reminders
  exports/       candidate PDF exports
  index/         public facts: professors, affiliations, papers (in progress, #233)
  workspace/     a student's matches, shortlist and corrections (in progress, #233)
  assistant/     Gradis chat
  cv/            documents (CVs, statements): Markdown text, tailoring, upload sandbox
  agents/        agent and tool registry
  providers/     per-account model settings
alembic/         migrations
tests/           pytest suite
```

See [docs/architecture.md](../docs/architecture.md) for how these fit together.

## Tests and checks

```bash
uv run pytest -q          # needs Postgres; uses a scratch graduator_test database
uv run ruff check .
uv run alembic revision --autogenerate -m "what changed"   # after editing models
```

The test suite creates and drops its own database, so it never touches your development data. Set `TEST_DATABASE_URL` to use a different one.

## Operations

Run these from the repo root:

```bash
make backup            # pg_dump to ./backups (see docs/backups.md)
make backup-verify     # restore the newest dump into a scratch database and check it
make usage-report      # model calls and tokens across accounts (DAYS=30)
make encrypt-secrets   # one-off: encrypt provider keys stored by older versions
```
