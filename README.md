<h1 align="center">Blesser</h1>

<p align="center">
  Making opportunities visible: grants, accelerators, fellowships, scholarships and more for startups, researchers and students in Ghana.
</p>

Blesser gathers opportunities into one public catalogue and helps people act on them. Agents search the web, read each opportunity's own page and add what they can verify. Anyone can browse the catalogue without an account. With an account, people can:

1. **Track** an opportunity in their applications, from saved to accepted, with its requirements as a checklist and deadline reminders 14, 7 and 1 days before.
2. **Plan** the work in to-dos linked to the opportunity or application.
3. **Sync** deadlines and dated to-dos to Google Calendar, Apple Calendar or Outlook, through a private subscription link, an `.ics` download or a Google Calendar link.
4. **Find more** by starting a scan and watching the agents work, or share an opportunity they know about.

Blesser started as a fork of [Graduator](https://github.com/esmond-adjei/graduator) (`b6747b4`) and keeps its agent loop, Postgres-backed task queue, accounts and notifications; everything specific to graduate-school research was removed.

## How it works

Two processes share one Postgres database:

- **API** (FastAPI): serves the web app, the public catalogue, and queues scans.
- **Worker**: claims scan tasks and runs the discovery agent: `search_web` and `fetch_page` to read the web, and `save_opportunity` to add to the catalogue.

A save is accepted only if it cites a page the agent fetched in the same task, that page names the opportunity, and any stated deadline appears on it. Duplicates merge into one listing. See [docs/opportunities.md](docs/opportunities.md).

```
api/        FastAPI app, agent worker, migrations, tests (Python 3.12, uv)
webapp/     React + TypeScript web app (Node 26, Vite, Tailwind)
docs/       Opportunities, deployment, notifications, email, sign-in, backups
ops/        Backup and restore scripts
```

## Quick start

You need Docker, [uv](https://docs.astral.sh/uv/) and Node 26 (`webapp/.nvmrc`).

```bash
make install                      # backend and web app dependencies
cp api/.env.example api/.env      # add LLM_API_KEY and TAVILY_API_KEY (or BRAVE_API_KEY)

make db                           # Postgres in Docker
make api                          # API on http://localhost:8000
make worker                       # agent worker (second terminal)
make web                          # web app on http://localhost:5173 (third terminal)
```

Migrations run when the API starts. `make help` lists every command.

## Development

```bash
make verify       # lint, backend tests, web tests and the type-checked build
make test         # backend suite on a scratch database
make revision MSG="describe the change"   # migration from model changes
```

## Deployment

The API and worker share one Docker image; the web app is a static build served by nginx, which also proxies `/api`.

```bash
make up           # web app on :8080, API on :8000
```

See [docs/deployment.md](docs/deployment.md) for production settings and wiring, and [docs/backups.md](docs/backups.md) for backups.
