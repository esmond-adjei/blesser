# Opportunities

Blesser lists grants, accelerators, incubators, fellowships, scholarships, internships, competitions and calls for proposals. A crawler finds candidate pages. Code removes duplicates and passed deadlines before a model extracts fields. Discovery agents search for gaps. Every save is checked against a fetched page. The public site shows the team's published public listings. Members also see published members-only finds, track applications, plan to-dos and sync deadlines to their calendars.

## What lives where

| Piece | Code | Notes |
|---|---|---|
| Catalogue | `api/api/opportunities/` | One shared `opportunities` table, deduplicated on normalized organization and title. |
| Public API | `api/api/public/` | Public response schema, visibility filters, slug redirects and cache headers. |
| Member API | `api/api/app/` and the feature routers | Member response schema, tracking, scans, applications, notifications and to-dos. |
| Admin API | `api/api/admin/` | Staff authentication, editorial changes, people management and auditing. |
| Curation | `api/api/editorial/` | Collections, versioned homepage content, settings, reports and slug history. |
| Crawling | `opportunities/crawler.py`, `page_cache.py`, `triage.py`, `pipeline.py` | Registered sources, persistent page cache, candidate triage and structured extraction. |
| Discovery | `opportunities/tasks.py`, `prompts.py`, `tools.py` | Category discovery and single-opportunity verification tasks. |
| Scans | `api/api/scans/` | Postgres-backed queue with leases, retries, traces and a reaper. |
| Tracking | `applications.opportunity_id` | Copies listing details into a member's private application. |
| Calendar | `todos/ics.py`, `todos/service.py` | Per-opportunity downloads and private calendar feeds. |

## How an agent save is grounded

`save_opportunity` refuses a save unless:

1. `source_url` is a page that `fetch_page` returned in the same task.
2. The page names the opportunity or its organization.
3. The complete calendar date of a stated deadline appears on the page. Passed deadlines are refused unless applications are rolling.
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

## Crawler-first scans

The worker crawls enabled sources on their due schedule and when staff request a crawl. Each scan's existing category tasks process the crawler pipeline before their discovery agent. Sweeps use the same tasks. The extraction budget defaults to eight pages per category, with at most eighty candidates examined so deterministic rejections do not consume model calls. This budget is separate from the existing opportunity save limits.

Sources can be RSS or Atom feeds, sitemaps, or HTML listings. Migration `0003` seeds seven sources checked live with BlesserBot on 9 November 2026: Wellcome funding schemes, DAAD Ghana funding, NEIP, Grand Challenges grant opportunities, the Tony Elumelu Foundation, Opportunities for Africans RSS and Opportunity Desk RSS. An unreachable Youth feed, a removed Gates Cambridge page and an old redirected Anzisha page were excluded.

The crawler removes navigation and sharing links, normalizes tracking parameters, and records new item URLs only once. Generic funding listings can expand into more candidates without a model call. Triage checks catalogue source URLs, application links, known dedupe keys, content hashes and explicit deadline dates. Publication dates do not count as deadlines. Ambiguous dates and pages with future or rolling application dates survive date triage.

One extraction request returns strict JSON on trimmed page text. It identifies a named open opportunity, its category, regional eligibility and confidence. The same grounding validator handles pipeline and agent saves. Missing required fields, invalid JSON, unsupported names and unsupported deadlines cannot be saved. Results below `EXTRACTION_MIN_CONFIDENCE` default to staff review. Regional exclusions and categories outside the requested scan remain available for later scans that match them.

The database page cache is shared across tasks, workers and scans, including failed fetches. It respects conditional GETs and robots.txt. Repeated fetches of the same window within a task return only a short reminder; a new offset can still read unseen text. Known catalogue and rejected URLs are suppressed before HTTP. Code-confirmed closed URLs become closed candidates. Agent irrelevance is recorded as a rejected outcome scoped to its category and region, so another scope can still consider the page. Domains that produce saves become disabled source proposals, unless the registry already contains that domain.

An agent no longer has to spend turns trying to save something when no useful leads remain. It stops after `DISCOVERY_NO_YIELD_TURNS` without a new save, default five, or `DISCOVERY_MAX_TURNS`, default twelve, and records a Saved/Skipped summary. The global `MAX_AGENT_TURNS` remains an additional ceiling. Explicit staff re-verification can still fetch a known opportunity and refresh its verified deadline.

Crawler settings live under `site_settings.crawler` and are editable in admin Settings. Config supplies defaults:

| Setting | Config default | Purpose |
|---|---|---|
| `hours` | `CRAWL_HOURS=6` | Crawl cadence; zero pauses automatic crawls, while explicit crawl requests still run. |
| `max_sources` | `CRAWL_MAX_SOURCES=12` | Sources per pass. |
| `max_items_per_source` | `CRAWL_MAX_ITEMS_PER_SOURCE=40` | Candidate links per source. |
| `max_candidates_per_task` | `CRAWL_MAX_CANDIDATES_PER_TASK=8` | Extraction budget per category. |
| `host_interval_seconds` | `CRAWL_HOST_INTERVAL_SECONDS=2` | Minimum time between host requests, across workers. |
| `page_cache_seconds` | `FETCH_CACHE_SECONDS=21600` | Shared page TTL. |

`EXTRACTION_MAX_CHARS=10000` bounds extraction text and `EXTRACTION_MIN_CONFIDENCE=0.85` sets the review threshold. Temporary page failures retry after 30 minutes. Rejected and closed outcomes remain recorded; staff can explicitly re-verify catalogue entries for a later cycle. Automated annual-cycle reactivation of rejected URLs is not implemented.

Editors can list, add, edit, enable, disable, delete and request crawls at `/api/admin/sources`. Deleting a source preserves its candidates and opportunities. Every staff write is audited. The Sources page shows candidates and saves, last-crawl yield, errors, failure counts and queued requests.

Scan and task responses add `metrics` without changing existing fields. Metrics distinguish candidates found and considered, extraction attempts and valid extractions, rejection reasons, new saves, model calls, input/output tokens and elapsed task time. `triaged_out` also includes post-extraction decisions such as regional exclusions and failed grounding. Its reasons distinguish these from deterministic rejections.

Run the reviewable probe with `cd api && uv run python -m scripts.scan_pipeline_probe --crawl-only --output ../.agent-logs/crawl.json`, then omit `--crawl-only` for a new three-category scan. It uses the existing enabled account with the earliest creation date and the worker claim/process path. It does not claim other scans. The scan run changes the dev catalogue according to publishing settings.
