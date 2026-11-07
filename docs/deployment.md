# Deployment

`api` and `worker` share one image (`api/Dockerfile`); the compose command decides the role. `webapp` is its own image (`webapp/Dockerfile`, Node 26 build served by nginx).

```bash
# Full stack
docker compose up -d --build db api worker webapp   # web app on :8080, api on :8000

# Backend only
docker compose up -d --build db api worker

# More workers (the queue is Postgres-backed and safe to scale)
docker compose up -d --scale worker=3
```

The API publishes port 8000 on `127.0.0.1` only (`API_BIND`); browsers reach it through the web app's nginx at `/api`. Request bodies are capped at 1 MB by the API (`MAX_REQUEST_BYTES`) and 2 MB by nginx.

Two wiring modes:

- **Same origin (the compose default):** build the web app with `VITE_API_URL` empty; nginx forwards `/api` to `api:8000`.
- **Split origins:** bake `VITE_API_URL=https://<api-host>` into the web app image, expose the API behind TLS (`API_BIND=0.0.0.0` or a proxy), list the web app's origin in `CORS_ORIGINS`, and set `PUBLIC_API_URL` so calendar subscription links point at the API.

## Before going live

- `AUTH_SECRET`: a long random value. It signs sessions and encrypts calendar links; changing it signs everyone out and invalidates every calendar link.
- `LLM_API_KEY` and a search key (`TAVILY_API_KEY` or `BRAVE_API_KEY`): without them scans fail. The API logs a warning at startup when either is missing.
- `APP_BASE_URL`: the public web app URL, used in emails and calendar events.
- `MAIL_BACKEND=smtp` and the `SMTP_*` settings ([email.md](email.md)), so verification, resets and reminders reach people.
- `OPS_ADMIN_EMAILS`, for publishing community submissions.
- Optional: `OPPORTUNITY_SWEEP_EMAIL` and `OPPORTUNITY_SWEEP_HOURS` for scheduled scans, VAPID keys for push ([notifications.md](notifications.md)), Google sign-in ([sign-in-providers.md](sign-in-providers.md)).

Scans cost model tokens and search calls. Each account may start 3 scans an hour and 10 a day (the `scan` limit in `api/api/core/ratelimit.py`), and each scan saves at most `MAX_OPPORTUNITIES_PER_RUN` opportunities.

## Persistent storage

Everything lives in Postgres, on the `blesser_pgdata` volume. Back it up as in [backups.md](backups.md).

## Local model (Ollama)

Set `LLM_PROVIDER=ollama`, `LLM_MODEL` to a model with tool calling, and `OLLAMA_MAX_CONCURRENCY` to the server's `OLLAMA_NUM_PARALLEL`, so workers send as many calls as it runs. A 32k context window is plenty.

## Migrations

Schema changes ship as Alembic revisions in `api/alembic/versions/` and are applied on boot. `0001_baseline` is the whole schema; add a revision for every model change:

```bash
make revision MSG="what changed"   # autogenerate from the models, then review it
```

`tests/test_migrations.py` checks a fresh upgrade, a downgrade cycle, and that the models and migrations agree.
