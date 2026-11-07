# Opportunities

Blesser makes opportunities visible: grants, accelerators, incubators, fellowships, scholarships, internships, competitions and calls for proposals open to startups, researchers and students in Ghana. Agents find them on the web and check each one against its own page. Anyone can browse the catalogue, without an account. Signed-in people can track opportunities, plan the work in to-dos and sync deadlines to their calendar.

## What lives where

| Piece | Code | Notes |
|---|---|---|
| Catalogue | `api/api/opportunities/` (`models.py`, `service.py`, `routes.py`) | One shared, public table: `opportunities`. Deduplicated on normalized organization + title (`dedupe_key`). |
| Discovery agent | `opportunities/tasks.py`, `prompts.py`, `tools.py` | Task type `discover_opportunities`, one per audience category, on the existing run queue. Its only write is `save_opportunity`. |
| Scans | `opportunities/scans.py` | A scan is a run whose field starts with `Opportunities:`. The run page shows its agents and their traces live. |
| Tracking | `applications.opportunity_id` | Tracking copies the opportunity into the person's application tracker. Status, checklist, notes and the 14/7/1-day deadline reminders then work as for any application. |
| To-dos | `api/api/todos/` | Private to-dos, optionally linked to an opportunity or an application. |
| Calendar | `todos/ics.py`, `todos/service.py` | A per-opportunity `.ics` download, a Google Calendar link, and a private subscription feed of deadlines and dated to-dos. |
| Web app | `webapp/src/pages/Opportunities.tsx`, `Todos.tsx`, `lib/opportunities.ts` | `/opportunities` is public (signed-out visitors get a light frame); `/todos` needs an account. |

## How an agent save is grounded

The catalogue is public, so a save has to show where its facts came from. `save_opportunity` (`opportunities/tools.py`) refuses a save unless:

1. `source_url` is a page that `fetch_page` returned **in the same task**. Every fetch records the page text on the task's `ToolContext.fetched_pages`.
2. The page names the opportunity: most of the title's distinctive words, or the organization's name, appear on it.
3. A stated deadline appears on the page (its year, plus its month or day). A deadline that has already passed is refused, unless the page says applications are rolling.
4. The task's and the scan's budgets have room (`MAX_OPPORTUNITIES_PER_TASK`, `MAX_OPPORTUNITIES_PER_RUN`).

A save of an opportunity already in the catalogue refreshes it rather than adding a duplicate. It fills empty fields, merges requirements, countries and tags, takes a newer cycle's deadline once the old one has passed, and stamps `verified_at`. It never overwrites a field that already has a value, and it never republishes a row an ops admin hid. Parallel tasks saving the same opportunity are serialized by a Postgres advisory lock on its key.

These checks catch a model that invents a page or a date. They do not prove a page is trustworthy. The detail view says who found the opportunity and when it was last checked, links the source page, and asks people to confirm on the official page before they apply.

## Moderation

- Agent saves publish straight away. Set `OPPORTUNITY_AUTO_PUBLISH=false` to hold them as `pending` instead.
- Community submissions (`POST /api/opportunities`) wait as `pending`, unless the person sharing is an ops admin.
- Ops admins (`OPS_ADMIN_EMAILS`, verified email) list the pending rows with `GET /api/opportunities/pending`, and publish, hold or hide one with `PATCH /api/opportunities/{id}/status`. There is no review screen in the web app yet.

## Keeping the catalogue fresh

People start scans from the Opportunities page with **Find more**. A scan is a normal run, so it uses the person's own model settings and counts against their plan's monthly run quota.

For an always-fresh public catalogue, set `OPPORTUNITY_SWEEP_EMAIL` to an existing account and `OPPORTUNITY_SWEEP_HOURS` to an interval, for example 24. Once an hour, the worker's housekeeping loop checks whether that account's newest scan is older than the interval and, if it is, starts a scan of every category in `OPPORTUNITY_DEFAULT_REGION`.

## API

| Method and path | Auth | What it does |
|---|---|---|
| `GET /api/opportunities` | none | Published opportunities, open ones by default. Filters: `q`, `category`, `kind`, `country`, `closing_within` (days), `include_closed`, `sort` (`deadline` or `new`), `limit`, `offset`. |
| `GET /api/opportunities/facets` | none | Open counts per category and kind, plus how many close within 14 days. |
| `GET /api/opportunities/{id}` | none | One published opportunity. |
| `GET /api/opportunities/{id}/calendar.ics` | none | The deadline as an all-day event, with reminders 7 days and 1 day before. |
| `POST /api/opportunities` | account | Share an opportunity (held for review). |
| `POST /api/opportunities/scans` | account | Start a scan: `{categories, region, focus}`. Returns `{run_id, tasks}`. |
| `POST /api/opportunities/{id}/track` | account | Add the opportunity to the application tracker (idempotent). |
| `GET /api/opportunities/tracked` | account | `{opportunity_id: application_id}`. |
| `GET /api/opportunities/pending`, `PATCH /api/opportunities/{id}/status` | ops admin | Moderation. |
| `GET/POST /api/todos`, `PATCH/DELETE /api/todos/{id}` | account | To-dos. `GET` takes `status=open|done|all`. |
| `GET /api/calendar/feed`, `POST /api/calendar/feed/rotate` | account | The private subscription URL, and a replacement for it. |
| `GET /api/calendar/feed/{token}.ics` | token | The feed: application deadlines still being worked on, and open to-dos with a due date, from 30 days ago on. |

The feed token is stored encrypted, with a SHA-256 hash for lookup, so the app can show the URL again. Rotating the token stops the old URL from working. Feed links use `PUBLIC_API_URL`, or `APP_BASE_URL` when the web app proxies `/api`.
