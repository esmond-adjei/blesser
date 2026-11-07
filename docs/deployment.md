# Deployment and migrations

## Deploy one app at a time

`api` and `worker` share one image (`api/Dockerfile`) — the compose
command decides the role. `webapp` is its own image (`webapp/Dockerfile`,
nginx serving the static build).

```bash
# Full stack locally
docker compose up -d --build db api worker webapp   # webapp on :8080, api on :8000

# Backend only (api + worker + db)
docker compose up -d --build db api worker

# Webapp only — needs VITE_API_URL pointed at a reachable api
VITE_API_URL=https://graduator-api.example.com docker compose up -d --build webapp

# More workers (db-backed queue, safe to scale)
docker compose up -d --scale worker=3
```

The api publishes port 8000 on `127.0.0.1` only (`API_BIND`); browsers
reach it through the webapp's nginx at `/api`. Request bodies are capped
by the api itself (10 MB CV upload, 5 MB avatar, 2 MB elsewhere,
`MAX_REQUEST_BYTES`), and nginx admits up to 12 MB on `/api/`.

Two wiring modes:

- **Same-origin (compose default):** build the webapp with `VITE_API_URL`
  empty; the browser calls `/api` on the webapp host and nginx forwards it
  to `api:8000`. Set `CORS_ORIGINS=*` (dev) or leave the default.
- **Split origins (webapp on its own host):** bake
  `VITE_API_URL=https://<api-host>` into the webapp image (set
  `API_BIND=0.0.0.0`, or put a TLS proxy in front of the api) and list the
  webapp origin in the api's `CORS_ORIGINS` (e.g.
  `CORS_ORIGINS=https://graduator.example.com`).

## The marketing site

`website/` is a separate static site (Astro). It never talks to the API:
no auth, no database, no account. It only links people into the app, so it
deploys on its own, from `main`, to GitHub Pages.

```bash
make site           # dev server on :4321
make site-build     # static build into website/dist
make site-preview   # serve the build
```

`.github/workflows/pages.yml` builds it and publishes it. These settings
come from repository variables (Settings → Secrets and variables →
Actions → Variables), not from the repository:

| Variable | What it is |
|---|---|
| `PAGES_DOMAIN` | The custom domain, e.g. `graduator.dev`. Written to `CNAME` at build time; leave it empty for a project site. |
| `PAGES_BASE_PATH` | The path the site is served from. `/graduator` for a project site, `/` for a custom domain. |
| `PUBLIC_SITE_URL` | Canonical origin of the site. Drives canonical links, the sitemap and `robots.txt`. |
| `PUBLIC_APP_URL` | Where the site's calls to action point: the app, e.g. `https://app.graduator.dev`. |
| `PUBLIC_CONTACT_EMAIL` | Address for privacy and removal requests on the legal pages. |

The webapp has one matching setting, `VITE_SITE_URL`: anonymous visitors
on the app's root are redirected to the site. Without it (local dev) the app
offers sign-in instead of redirecting.

A project site served from a subpath (`https://<user>.github.io/<repo>/`)
needs `PAGES_BASE_PATH=/<repo>`; a custom domain serves from `/`.

## Persistent storage

Two things must survive a rebuild: Postgres and the CV storage directory.
Compose keeps both on named volumes:

| Volume | Mounted at | Holds |
|---|---|---|
| `graduator_pgdata` | `db:/var/lib/postgresql/data` | every table |
| `graduator_cv_storage` | `api` and `worker`: `/app/cv_storage` | uploaded document files and data-export archives (document text and versions are in Postgres) |

Compose sets `CV_STORAGE_DIR=/app/cv_storage` on both services, so a
relative value in `api/.env` can't move files back into the container
layer. Outside compose, set `CV_STORAGE_DIR` to an absolute path on
persistent storage. If the directory is lost while the DB survives,
the documents' text survives but their original uploads can't be downloaded.

Check it after deploying:

```bash
# upload a CV in the app, then
docker compose up -d --build --force-recreate api
# the original upload still downloads
```

Back the volume up with the database (see [backups.md](backups.md)).

## Local model (Ollama)

Measured on past runs (#180), no model call exceeded about 19k tokens of
context, so a 262k context window only spends VRAM that could serve more
requests in parallel. On the Ollama host:

```bash
OLLAMA_CONTEXT_LENGTH=32768   # headroom over the largest call seen
OLLAMA_NUM_PARALLEL=4         # or what VRAM allows at that context
```

Then set `OLLAMA_MAX_CONCURRENCY` in `api/.env` to the same number as
`OLLAMA_NUM_PARALLEL`, so workers send as many calls as the server runs.

Short single-purpose calls (the code-first save of a likely match, email
drafts) don't need the large model. Set `LLM_SMALL_MODEL` to a smaller
model on the same provider and endpoint (for example `qwen3:8b`) and
they use it instead, while discovery, faculty lists and the full research
loop keep `LLM_MODEL`. It applies to runs on the system model (Auto); a
run on someone's own model keeps that model for every call.

## Migrations

Schema changes ship as Alembic revisions in `api/alembic/versions/`,
applied automatically on boot (`init_db` runs `alembic upgrade head`).
Operator commands for manual control (from `api`):

```bash
cd api
uv run alembic upgrade head     # apply pending migrations
uv run alembic history          # show applied/pending revisions
uv run alembic stamp 001        # one-time: databases created before Alembic
                                # (tables exist, no version row) — then boot
                                # upgrades 001 → head by itself
```

New schema change? Edit the models, then generate the diff (never hand-write table DDL):

```bash
uv run alembic revision --autogenerate -m "what changed"
```

`tests/test_migrations.py` covers fresh upgrades, legacy upgrades, and a downgrade cycle on scratch databases.
