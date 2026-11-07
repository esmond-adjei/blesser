<p align="center">
  <img src="webapp/public/mascot-states/happy.png" alt="Gradis, the mascot Blesser inherits from Graduator" width="140">
</p>

<h1 align="center">Blesser</h1>

<p align="center">
  Making opportunities visible: grants, accelerators, fellowships, scholarships and more for startups, researchers and students in Ghana.
</p>

Blesser gathers opportunities into one public catalogue and helps people act on them. Agents search the web, read each opportunity's own page and add what they can verify. Anyone can browse the catalogue without an account. With an account, people can:

1. **Track** an opportunity. It joins their application tracker with its status, requirements checklist and deadline reminders.
2. **Plan** the work in to-dos linked to the opportunity or application.
3. **Sync** deadlines and dated to-dos to Google Calendar, Apple Calendar or Outlook, through a private subscription link, an `.ics` download or a Google Calendar link.
4. **Find more** by starting a scan and watching the agents work, or share an opportunity they know about.

Blesser is a fork of [Graduator](https://github.com/esmond-adjei/graduator) (at `b6747b4`) and keeps all of its features: the agent orchestrator and run queue, application tracking, notifications, the Gradis assistant, and graduate programme and supervisor research for students and researchers.

## Features

- **Opportunity catalogue.** Public and filterable by audience (startups, researchers, students), kind, country, closing date and keyword. See [docs/opportunities.md](docs/opportunities.md).
- **Grounded discovery agents.** A save must cite a page the agent fetched in the same task, the page must name the opportunity, and a stated deadline must appear on it. Duplicates merge into one row.
- **Scheduled sweeps.** Optionally, the worker refreshes the catalogue every N hours.
- **Tracking and reminders.** Tracked opportunities live in Applications, with reminders 14, 7 and 1 days before each deadline (inbox, push or email).
- **To-dos and calendar sync.** A to-do list grouped by due date, and one private iCalendar feed that covers both deadlines and to-dos.
- **Community submissions.** Signed-in people can share opportunities; ops admins publish them.
- **Everything from Graduator.** Discovery runs, Dossier, Outbox, CV curator, Gradis, Flows, bring-your-own-model, data export.

## How it works

<img src="webapp/public/mascot-states/reading.png" alt="" width="110" align="right">

Blesser has two processes that share one Postgres database:

- **API** (FastAPI): serves the web app and adds agent work to a queue.
- **Worker**: picks up queued tasks and runs the agent loop.

The agent decides what to look at next. The tools it calls are deterministic: publication data comes from [OpenAlex](https://openalex.org), and every write goes through a fixed schema. That means the agent can only report what a tool actually returned.

Budgets cap how much work each task and run can do. Progress is saved after every turn, so a crashed worker picks up where it left off.

See [docs/architecture.md](docs/architecture.md) for the full design.

```
api/        FastAPI app, agent worker, migrations, tests
webapp/     React + TypeScript dashboard (Vite, Tailwind)
website/    Marketing site (Astro, static build)
docs/       Architecture, reference, deployment and data handling
```

## Quick start

You need Docker, [uv](https://docs.astral.sh/uv/) and Node 22.

```bash
make install                      # backend and frontend dependencies
cp api/.env.example api/.env      # add your model key (see below)

make db                           # Postgres in Docker
make api                          # API on http://localhost:8000
make worker                       # agent worker (second terminal)
make web                          # web app on http://localhost:5173 (third terminal)
```

Database migrations run automatically when the API starts. Run `make help` to see every command.

### Keys

Set these in `api/.env`:

| Variable | Needed for |
|---|---|
| `LLM_PROVIDER`, `LLM_API_KEY` | The agent. Use `ollama` to run locally with no key. |
| `TAVILY_API_KEY` or `BRAVE_API_KEY` | Programme and faculty search. Without either, discovery works only from URLs the agent already knows (keyless DuckDuckGo is opt-in via `SEARCH_PROVIDERS`). |
| `EMBEDDING_PROVIDER`, `EMBEDDING_API_KEY` | Fit scores. Without a key, scoring falls back to keyword overlap. |
| `AUTH_SECRET` | Signs sign-in tokens. Required in production. |

Every other setting is listed, with its default, in [`api/.env.example`](api/.env.example).

## Development

<img src="webapp/public/mascot-states/error-gear.png" alt="" width="100" align="right">

```bash
make verify       # lint, backend tests and type-checked web build in one go
make test         # backend suite on a scratch database (never touches your dev data)
make revision MSG="describe the change"   # create a migration from model changes
```

Run `make lint` before opening a PR. CI runs the same checks.

## Deployment

The API and the worker share one Docker image; the web app is a static build served by nginx. The marketing site (`website/`) is a separate static build deployed to GitHub Pages. To run the full stack locally:

```bash
make up           # web app on :8080, API on :8000
make site         # marketing site on :4321
```

To deploy the apps separately, scale workers, or set up cross-origin hosting, see [docs/deployment.md](docs/deployment.md). Before going live, work through the [production checklist](docs/production-checklist.md).

```bash
make backup           # dump Postgres to ./backups
make backup-verify    # restore the newest dump into a scratch database and check it
make encrypt-secrets  # one-off: encrypt provider keys stored by older versions
```

## Documentation

| Doc | What's inside |
|---|---|
| [Architecture](docs/architecture.md) | Design decisions, how a run flows, budgets, crash recovery, observability |
| [Deployment](docs/deployment.md) | Docker images, hosting topologies, migrations |
| [Production checklist](docs/production-checklist.md) | What's been hardened before launch |
| [Production readiness review](docs/production-readiness-review.md) · [Architecture upgrades](docs/architecture-upgrades.md) | Open production and scaling work, and a proposal for it |
| [Backups](docs/backups.md) | What's backed up, scheduling, restore drills |
| [Email](docs/email.md) · [Sign-in providers](docs/sign-in-providers.md) | SMTP setup; Google OAuth client setup |
| [Notifications](docs/notifications.md) | Inbox, browser push (VAPID keys) and email notifications; deadline reminders |
| [Plans](docs/plans.md) · [Flows](docs/flows.md) · [Fallbacks](docs/fallbacks.md) · [Verification sources](docs/verification-sources.md) | Paywalls, custom pipelines, external-service fallbacks, sources beyond OpenAlex |
| [Opportunities](docs/opportunities.md) | The catalogue, grounded discovery agents, moderation, sweeps, to-dos and calendar feeds |
| [CV sandbox](docs/cv-sandbox.md) | How uploaded documents are isolated |
| [Data handling](docs/data-handling.md) | What is sent to LLM providers, and what is stored |

See [CHANGELOG.md](CHANGELOG.md) for what changed in each release.
