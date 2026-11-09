# Opportunities

Blesser lists grants, accelerators, incubators, fellowships, scholarships, internships, competitions and calls for proposals. Agents find opportunities and check each one against a page they fetched. The public site shows the team's published public listings. Members also see published members-only finds, track applications, plan to-dos and sync deadlines to their calendars.

## What lives where

| Piece | Code | Notes |
|---|---|---|
| Catalogue | `api/api/opportunities/` | One shared `opportunities` table, deduplicated on normalized organization and title. |
| Public API | `api/api/public/` | Public response schema, visibility filters, slug redirects and cache headers. |
| Member API | `api/api/app/` and the feature routers | Member response schema, tracking, scans, applications, notifications and to-dos. |
| Admin API | `api/api/admin/` | Staff authentication, editorial changes, people management and auditing. |
| Curation | `api/api/editorial/` | Collections, versioned homepage content, settings, reports and slug history. |
| Discovery | `opportunities/tasks.py`, `prompts.py`, `tools.py` | Category discovery and single-opportunity verification tasks. |
| Scans | `api/api/scans/` | Postgres-backed queue with leases, retries, traces and a reaper. |
| Tracking | `applications.opportunity_id` | Copies listing details into a member's private application. |
| Calendar | `todos/ics.py`, `todos/service.py` | Per-opportunity downloads and private calendar feeds. |

## How an agent save is grounded

`save_opportunity` refuses a save unless:

1. `source_url` is a page that `fetch_page` returned in the same task.
2. The page names the opportunity or its organization.
3. A stated deadline appears on the page. Passed deadlines are refused unless applications are rolling.
4. The task and scan have room in their opportunity budgets.

An existing listing is refreshed instead of duplicated. Agent saves fill empty fields, merge requirements, countries and tags, replace a passed deadline with a verified newer cycle, and stamp `verified_at`. They preserve editorial status and audience, including hidden rows. A Postgres advisory lock serializes saves on the dedupe key.

These checks establish where the facts came from. They do not establish whether a source is trustworthy. Members should confirm details on the official page before applying.

## Moderation

The binding fields and response shapes are in [api-contract.md](api-contract.md).

| Status | Public site | Member catalogue | Admin |
|---|---|---|---|
| `draft` | No | No | Yes |
| `in_review` | No | No | Yes |
| `published` | Only `audience = public` | Both audiences | Yes |
| `archived` | Detail by public slug, with `closed: true` | Existing tracked copies only | Yes |
| `hidden` | 404 | Existing tracked copies only | Yes |

Publishing defaults live in `site_settings`. Agent finds default to `published` with `audience = members`. Community submissions default to `in_review`, with `review_reason = new_submission`. Agent finds held in review use `review_reason = agent_find`. Reports create an unresolved report and mark the listing `reported` for staff review without immediately removing it from the catalogue.

Editors manage opportunities, bulk actions, duplicates, verification tasks, reports, collections, homepage content and scans. Admins also manage users, settings and audit history. Every admin write appends an audit row in the same transaction as the change. Staff cannot read members' applications, notes or to-dos through admin routes.

Accounts have a persisted `member`, `editor` or `admin` role. `OPS_ADMIN_EMAILS` only seeds verified member accounts as admins at boot. Disabled accounts cannot authenticate. Staff access tokens have `aud = admin`; member tokens have `aud = app`. Staff refresh grants last 12 hours. Each audience rejects the other's access and refresh tokens.

Public listings have unique slugs. Changing a slug records the old one for a 301 redirect to the current slug. Redirects obey the current listing's status and audience. Historical slugs cannot be assigned to another listing.

## Keeping the catalogue fresh

Member scan quotas default to 3 per hour and 10 per day. Admin settings can change those limits and the discovery publishing defaults. Staff scans bypass member quotas.

Set `OPPORTUNITY_SWEEP_EMAIL` to an existing enabled account and configure `sweep_hours` through admin settings to enable scheduled scans. The worker checks hourly and starts a scan across all categories when the account's last scan is old enough.

The worker also runs an archive pass once per UTC date. With `auto_archive = true`, it archives published opportunities whose `deadline_date` is before today. Rolling opportunities are skipped. Existing tracked applications retain their copied listing details.

## API

Public GET responses send `Cache-Control: public, max-age=60, s-maxage=300, stale-while-revalidate=3600`. Public schemas omit internal status, source, scan IDs, account IDs, editor notes, review reasons and traces. Public submissions are limited to 5 per IP per hour; reports to 10 per IP per hour.

| Method and path | Auth | What it does |
|---|---|---|
| `GET /api/public/opportunities` | None | Published public listings, open by default. Filters: `q`, `category`, `kind`, `country`, `closing_within`, `include_closed`, `sort=deadline\|new`, `limit` up to 100, `offset`. |
| `GET /api/public/opportunities/{slug}` | None | Public listing or archived closed marker; old slugs redirect. |
| `GET /api/public/opportunities/{slug}/calendar.ics` | None | Deadline event. |
| `GET /api/public/facets` | None | Open public category and kind counts, total and closing-soon count. |
| `GET /api/public/collections`, `GET /api/public/collections/{slug}` | None | Published public collections with visible listings, up to 12 items per collection on the list route. |
| `GET /api/public/site`, `GET /api/public/sitemap` | None | Current homepage content, active announcement, featured and closing-soon listings; sitemap data. |
| `POST /api/public/submissions` | None | Share a listing, with optional email. Returns `201 {id}`. |
| `POST /api/public/opportunities/{slug}/report` | None | Report a problem, with optional email. Returns 202. |
| `GET /api/app/opportunities`, `GET /api/app/opportunities/{id_or_slug}` | Member | Published listings of either audience. List supports public filters plus `new=true` and `audience=members\|public`. |
| `GET /api/app/opportunities/facets` | Member | Counts of listings members can see. |
| `POST /api/app/opportunities` | Member | Share a listing using the community publishing default. |
| `POST /api/app/opportunities/{id}/track`, `GET /api/app/opportunities/tracked` | Member | Track idempotently; read the member's opportunity-to-application map. |
| `/api/app/auth/*` | As appropriate | Existing account flows; register accepts an optional `track` slug. |
| `/api/app/applications`, `/api/app/todos`, `/api/app/notifications`, `/api/app/calendar/*` | Member or feed token | Existing private application, to-do, notification and calendar routes. |
| `/api/app/scans` | Member | Start, list, inspect, cancel and delete the member's scans. |
| `POST /api/admin/auth/login`, `POST /api/admin/auth/refresh`, `POST /api/admin/auth/logout`, `GET /api/admin/auth/me` | Staff credentials or staff token | Separate staff sessions. Login requires a verified, enabled editor or admin. |
| `GET/POST /api/admin/opportunities`, `GET/PATCH/DELETE /api/admin/opportunities/{id}` | Editor | Catalogue editing, including drafts, audience, slug, notes and featured rank. Detail includes the last 20 audit entries and a source trace excerpt. |
| `GET /api/admin/opportunities/counts`, `POST /api/admin/opportunities/bulk` | Editor | Editorial counts and bulk publish, archive, hide or review. |
| `POST /api/admin/opportunities/{id}/merge`, `POST /api/admin/opportunities/{id}/reverify` | Editor | Hide a duplicate and re-point tracking; queue one verification task. |
| `GET /api/admin/reports`, `PATCH /api/admin/reports/{id}` | Editor | Read reports and mark them resolved. |
| `GET/POST /api/admin/collections`, `PATCH/DELETE /api/admin/collections/{id}` | Editor | Curated items or saved catalogue filters. |
| `GET/PUT /api/admin/site` | Editor | Read and publish versioned homepage content. |
| `GET/POST /api/admin/scans` | Editor | All scans with owner email and traces; start a scan. |
| `GET/PUT /api/admin/settings` | Admin | Publishing defaults, archiving, member scan quotas and sweep interval. |
| `GET /api/admin/users`, `PATCH /api/admin/users/{id}` | Admin | Search users, change roles and disable accounts. Self-demotion and removal of the last active admin are blocked. |
| `GET /api/admin/audit` | Admin | Filter append-only audit entries. |

Existing member paths under `/api/*` remain aliases for one release. The old pending-list and status-moderation routes are removed.

Private calendar feed tokens are stored encrypted, with a SHA-256 hash for lookup. Rotation invalidates the previous URL; disabled accounts' feeds stop working. Links use `PUBLIC_API_URL`, or `APP_BASE_URL` when the web app proxies `/api`.
