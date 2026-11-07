# Blesser API

The FastAPI backend and the agent worker. One Docker image runs both; the start command decides which.

## Run it

Start Postgres first (`make db` from the repo root), then:

```bash
uv sync --group dev
cp .env.example .env                   # add your model and search keys

uv run uvicorn api.main:app --reload   # API on http://localhost:8000
uv run python -m api.worker            # agent worker, in a second terminal
```

Migrations run when the API starts. Interactive API docs are at http://localhost:8000/docs.

## Configuration

Every setting is in [`.env.example`](.env.example). The ones you need:

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY` | The discovery agent's model: `anthropic` (default), `openai`, `gemini`, `ollama` or `openai-compatible`. |
| `TAVILY_API_KEY`, `BRAVE_API_KEY` | Web search for scans, tried in the order of `SEARCH_PROVIDERS`. |
| `DATABASE_URL` | Postgres, the only supported database. |
| `AUTH_SECRET` | Signs sign-in tokens and encrypts calendar links. Required in production. |
| `MAIL_BACKEND`, `SMTP_*`, `APP_BASE_URL` | Password resets, verification and reminder emails ([docs/email.md](../docs/email.md)). |
| `OPPORTUNITY_SWEEP_EMAIL`, `OPPORTUNITY_SWEEP_HOURS` | Optional scheduled scans that keep the catalogue fresh. |
| `OPS_ADMIN_EMAILS` | Who may publish community submissions. |

## Layout

```
api/
  main.py          app, /ready, routers
  worker.py        worker entry point
  web.py           web search and page fetches (cached, robots.txt-aware, public addresses only)
  opportunities/   the public catalogue, save_opportunity grounding, the discovery prompt and task, sweeps
  scans/           scans and their task queue: leases, retries, the reaper, the worker loops
  agent/           the agent loop, tool definitions and dispatch, model providers
  applications/    the application tracker
  todos/           to-dos and the private iCalendar feed
  notifications/   inbox, browser push, email, deadline reminders and digests
  auth/            accounts, sessions, Google sign-in, email flows
  core/            config, database, mail, rate limits, egress guard
alembic/           migrations (0001 is the baseline)
tests/             the suite, run against a scratch database
```

## Tests

```bash
make test                 # from the repo root; needs Postgres
```

The suite creates and migrates its own scratch database (`TEST_DATABASE_URL`, default `blesser_test`). `tests/test_migrations.py` fails if the models and migrations drift apart: add a migration with `make revision MSG="..."`.
