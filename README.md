<h1 align="center">Blesser</h1>

<p align="center">
  Making opportunities visible: grants, accelerators, fellowships, scholarships and more for startups, researchers and students in Ghana.
</p>

Blesser gathers opportunities into one public catalogue and helps people act on them. Agents search the web, read each opportunity's own page and add what they can verify. Anyone can browse the catalogue without an account. With an account, people can:

1. **Track** an opportunity in their applications, from saved to accepted, with its requirements as a checklist and deadline reminders 14, 7 and 1 days before.
2. **Plan** the work in to-dos linked to the opportunity or application.
3. **Sync** deadlines and dated to-dos to Google Calendar, Apple Calendar or Outlook, through a private subscription link, an `.ics` download or a Google Calendar link.
4. **Find more** by starting a scan and watching the agents work, or share an opportunity they know about.
5. **Ask** the Assistant about opportunities, applications and to-dos, and let it track an opportunity or add a to-do once they confirm.
6. **Apply faster** with the Apply kit (profile, projects, documents and saved answers) and the browser extension that fills application forms from it.

Notifications (in-app, browser push and email) cover deadline reminders and scan results. See [docs/notifications.md](docs/notifications.md).

## How it works

Two processes share one Postgres database:

- **API** (FastAPI): serves the member app, the public site, the admin console and the extension, and queues scans.
- **Worker**: claims scan tasks and runs the discovery agent: `search_web` and `fetch_page` to read the web, and `save_opportunity` to add to the catalogue.

A save is accepted only if it cites a page the agent fetched in the same task, that page names the opportunity, and any stated deadline appears on it. Duplicates merge into one listing. See [docs/opportunities.md](docs/opportunities.md).

```
api/            FastAPI app, agent worker, migrations, tests (Python 3.12, uv)
webapp/         Member app: React + TypeScript (Node 26, Vite, Tailwind)
site/           Public site: Astro, server-rendered, reads /api/public
admin/          Admin console: React + TypeScript, for editors and admins
extension/      Browser extension that fills forms from the Apply kit (Manifest V3)
design-system/  @blesser/ui: tokens, components and assets shared by every front end
docs/           Architecture, API contract, opportunities, notifications, email,
                sign-in, applicant kit, extension, design system, deployment, backups
ops/            Backup and restore scripts
```

## Quick start

You need Docker, [uv](https://docs.astral.sh/uv/) and Node 26 (`.nvmrc`).

```bash
make install                      # backend and web app dependencies
cp api/.env.example api/.env      # add LLM_API_KEY and TAVILY_API_KEY (or BRAVE_API_KEY)

make db                           # Postgres in Docker
make api                          # API on http://localhost:8000
make worker                       # agent worker (second terminal)
make web                          # member app on http://localhost:5173 (third terminal)
make site                         # public site on http://localhost:4321 (fourth terminal)
make admin                        # admin console on http://localhost:5174 (optional)
```

Signed-out visitors at http://localhost:5173 are sent to the public site, so run `make site` too, or set `VITE_SITE_URL=` (empty) in `webapp/.env` to send them to the sign-in page instead. Migrations run when the API starts. `make help` lists every command.

## Development

```bash
make verify       # lint, backend tests, web tests and the type-checked build
make test         # backend suite on a scratch database
make revision MSG="describe the change"   # migration from model changes
```

## Deployment

The API and worker share one Docker image. The member app and admin console are static builds served by nginx, which also proxies `/api`. The public site runs on Node.

```bash
make up           # member app :8080, admin :8081, site :8082, API :8000
```

See [docs/deployment.md](docs/deployment.md) for production settings and wiring, and [docs/backups.md](docs/backups.md) for backups.
