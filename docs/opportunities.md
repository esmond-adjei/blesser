# Opportunities

Blesser lists grants, accelerators, incubators, fellowships, scholarships, internships, competitions and calls for proposals. A crawler finds candidate pages. Code removes duplicates and passed deadlines before a model extracts fields. Discovery agents search for gaps. Every save is checked against a fetched page. The public site shows the team's published public listings. Members also see published members-only finds, track applications, plan to-dos and sync deadlines to their calendars.

## What lives where

| Piece | Code | Notes |
|---|---|---|
| Catalogue | `api/api/opportunities/` | One shared `opportunities` table, deduplicated on a cycle-aware key of organization and title (`dedupe.py`). |
| Listing checks | `opportunities/freshness.py`, `archive.py` | Scheduled re-checks, undated expiry and new-cycle watch. |
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

An existing listing is refreshed instead of duplicated. Agent saves fill empty fields, merge requirements, countries and tags, replace a passed deadline with a verified newer cycle, and stamp `verified_at`. They preserve editorial status and audience, including hidden rows, with one exception: an archived listing whose deadline passed (or that expired as stale) is reopened when a save confirms a new cycle with a deadline ahead or rolling applications. It takes the new cycle's title, and goes to review instead when the extraction was unsure. A staff archive of a listing with a future deadline is never reopened. A Postgres advisory lock serializes saves on the dedupe key.

## Duplicates

The dedupe key is the normalized organization plus the normalized title, without what changes between cycles of one scheme:

- Years and year ranges ("2026", "2026/27").
- Cycle phrases: "call for applications" (or proposals, entries, nominations), "applications now open", "apply now", and cycle words with their number ("cohort 5", "6th cohort", "round 3", "intake", "edition", "cycle", "batch").
- A leading "the" and trailing "foundation", "trust", "fund", "ltd" and similar words on the organization, so "Wellcome" and "Wellcome Trust" match.

So "Mastercard Foundation Scholars Program 2027" refreshes the "Mastercard Foundation Scholars Program" row instead of adding a second one. Two genuinely different schemes whose names differ only by those words also share a key; staff can split them by editing the title.

Organizations written in unrelated ways ("DAAD" and "German Academic Exchange Service") are mapped by the `organization_aliases` table, which migration `0011` seeds with a few common Ghana funders. Editors manage it on the admin Duplicates page; a change re-keys existing listings unless another listing already holds the new key.

The Duplicates page lists pairs that the key did not catch: titles with trigram similarity of 0.5 or more (`pg_trgm`) from the same or a similar organization, and listings that share a source page. Editors keep one listing of a pair or mark the pair as different, which hides it from the list for good. Keeping one merges the other into it: tracking, to-dos, reports, scan results, collection places and crawl candidates move over, empty fields are filled, tags, countries and requirements are combined, the later `verified_at` is kept, and the merged listing's public link redirects to the kept one. The merged listing is hidden, not deleted.

Migration `0011` re-keys the existing catalogue. Where two rows now share a key, the published (then most recently verified) row takes it and the others keep `<key>#<id>`, so they appear on the Duplicates page for an editor to merge.

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

The worker also runs an archive pass once per UTC date. With `auto_archive = true`, it archives published opportunities whose `deadline_date` is before today. Rolling opportunities are skipped. It also archives undated and rolling listings that nothing has confirmed (`verified_at`, else `created_at`) for `freshness.stale_days`, default 120, with `check_outcome = stale`, so an undated listing does not stay open forever. Existing tracked applications retain their copied listing details.

### Scheduled listing checks

Every 15 minutes the worker claims up to `freshness.max_checks` listings (default 10) that are due, most urgent first:

1. Published, closing within `closing_days` (7), and not confirmed for `closing_recheck_days` (14).
2. Published with no deadline, or rolling, and not confirmed for `recheck_days` (30).
3. Archived, with a deadline in the last 400 days or none, and not checked for `cycle_days` (30).

Claiming stamps `checked_at`, so workers never check the same listing twice and a failed check is retried a day later. A listing with a check task already queued is skipped, and listings with no source page or link are left to the expiry rule.

A check reads the source page through the shared page cache first, without a model:

| Page | Published listing | Archived listing |
|---|---|---|
| 404 or 410, or redirected to a homepage | To review, `review_reason = source_changed` | Recorded |
| Same content hash as when last confirmed | `verified_at` stamped | Recorded |
| Every stated deadline has passed | Undated or rolling: archived (to review when `auto_archive` is off). Dated: to review, since the page disagrees | Recorded |
| Shows a deadline ahead or rolling applications | Agent check | Agent check |
| Otherwise changed | Agent check | Recorded as closed |
| Unreachable (timeouts, 5xx, robots) | Nothing changes; retried in a day | Same |

An agent check is a `reverify_opportunity` task, at most `max_agent_checks` (20) a day, grouped into one scan per pass with the focus "Scheduled listing checks". These scans belong to `OPPORTUNITY_SWEEP_EMAIL`'s account, or the earliest active admin, and send no "scan finished" notification; without either account, changed pages are recorded and retried later. The agent re-reads the page and saves the current facts through the usual grounding checks. A confirmed save stamps `verified_at` and stores the page's content hash, so the next check of an unchanged page needs no model. For an archived listing the save reopens it (see above). When a scheduled check cannot confirm a published listing, the listing goes to review with `review_reason = source_changed`; a staff-requested check only records `check_outcome = unconfirmed`.

Each listing keeps `checked_at`, `check_outcome` and `source_hash`. Members already see "Checked N days ago" from `verified_at`. Staff see both on the admin listing. The settings are editable under "Listing checks" in admin Settings.

## Search and matching

Code: `api/api/matching/` (profile, scoring, saved searches, alerts) and the list in `opportunities/service.py`.

**Search.** `opportunities.search_vector` is a stored generated `tsvector` (English stemming) with a GIN index. It weighs the title highest, then the funder, kind and tags, then the summary and location, then eligibility. Each word in `q` must match as a stemmed prefix, so "scholarships" finds "scholarship" and "schol" finds both while still typing. A query of only stop words ("the", "for") filters nothing. `sort=relevance` ranks by `ts_rank_cd`, then deadline. The web app uses it by default while there are search words; the public API and the Assistant's catalogue search accept it too.

**What you're looking for.** A member's `match_profiles` row holds categories, kinds, fields of study or sectors (free text), stages (`undergraduate`, `masters`, `phd`, `postdoc`, `founder`) and countries they can apply from. Before it is saved, `GET /api/app/match-profile` suggests one from the Applicant Kit: nationality and country of residence, the latest education entry's stage (a finished degree points at the next stage), its field, and the first skills. Only the plain profile column is read, never the encrypted identity fields.

**For you.** `sort=for_you` scores each listing in SQL (`matching/service.py`):

| Signal | Points |
|---|---|
| Category is one of the member's | 3 |
| Kind is one of the member's | 2 |
| Each field the listing text mentions (first 8 fields, at most 2 count) | 1.5 |
| A stage word (for example "masters", "PhD", "startup") | 1 |
| Closes in 7 to 30 days (0 to 6 days: 0.5) | 1 |
| Verified in the last 30 days | 0.5 |
| Added in the last 7 days | 0.5 |

Ties fall back to the soonest deadline. A listing whose `countries` names only specific countries, none of them the member's, is left out. Regions ("West Africa"), "Global" and an empty list keep it in, so an unclear listing is never hidden. Country names are matched after folding case, accents and punctuation, with aliases such as "Ivory Coast" and "UK" (`matching/geo.py`). Rows carry `match_score` and `match_terms` (the member's fields the listing mentions); the web app shows "Fits ..." on each card.

**Saved searches.** Up to 20 per member: a name, the list filters (`q`, `category`, `kind`, `country`, `closing_within`) and an alert frequency.

**Alerts.** The worker's hourly pass (`matching/alerts.py`) runs from 08:00 in the member's timezone:

- `new_match`: listings published since the last alert that fit the profile, daily or weekly. A fit passes the country check and matches each kind of preference the member set among categories, kinds and fields. A profile with only countries gets no alerts.
- `closing_match`: once a week, fitting listings that close within 14 days.
- `saved_search`: listings published since the last alert that match a saved search.

Each run makes at most one notification per member and kind (one per saved search), listing up to 10 listings, with the full list in the email. Tracked listings are left out. Alerts never look back more than 8 days, and turning alerts on starts from that moment. Notification settings decide push and email; with email off for a kind, the daily digest carries it.

## API

Public GET responses send `Cache-Control: public, max-age=60, s-maxage=300, stale-while-revalidate=3600`. Public schemas omit internal status, source, scan IDs, account IDs, editor notes, review reasons and traces. Public submissions are limited to 5 per IP per hour; reports to 10 per IP per hour.

| Method and path | Auth | What it does |
|---|---|---|
| `GET /api/public/opportunities` | None | Published public listings, open by default. Filters: `q`, `category`, `kind`, `country`, `closing_within`, `include_closed`, `sort=deadline\|new\|relevance`, `limit` up to 100, `offset`. |
| `GET /api/public/opportunities/{slug}` | None | Public listing or archived closed marker; old slugs redirect. |
| `GET /api/public/opportunities/{slug}/calendar.ics` | None | Deadline event. |
| `GET /api/public/facets` | None | Open public category and kind counts, total and closing-soon count. |
| `GET /api/public/collections`, `GET /api/public/collections/{slug}` | None | Published public collections with visible listings, up to 12 items per collection on the list route. |
| `GET /api/public/site`, `GET /api/public/sitemap` | None | Current homepage content, active announcement, featured and closing-soon listings; sitemap data. |
| `POST /api/public/submissions` | None | Share a listing, with optional email. Returns `201 {id}`. |
| `POST /api/public/opportunities/{slug}/report` | None | Report a problem, with optional email. Returns 202. |
| `GET /api/app/opportunities`, `GET /api/app/opportunities/{id_or_slug}` | Member | Published listings of either audience. List supports public filters plus `new=true`, `audience=members\|public` and `sort=for_you`. |
| `GET`/`PUT`/`DELETE /api/app/match-profile` | Member | What the member is looking for. `GET` returns `saved: false` and a suggestion from the Applicant Kit until one is saved. |
| `GET`/`POST /api/app/saved-searches`, `PATCH`/`DELETE /api/app/saved-searches/{id}` | Member | Saved searches with `alerts=off\|daily\|weekly`; up to 20 (`409` past that). |
| `GET /api/app/opportunities/facets` | Member | Counts of listings members can see. |
| `POST /api/app/opportunities` | Member | Share a listing using the community publishing default. |
| `POST /api/app/opportunities/{id}/track`, `GET /api/app/opportunities/tracked` | Member | Track idempotently; read the member's opportunity-to-application map. |
| `/api/app/auth/*` | As appropriate | Existing account flows; register accepts an optional `track` slug. |
| `/api/app/applications`, `/api/app/todos`, `/api/app/notifications`, `/api/app/calendar/*` | Member or feed token | Existing private application, to-do, notification and calendar routes. |
| `/api/app/scans` | Member | Start, list, inspect, cancel and delete the member's scans. |
| `POST /api/admin/auth/login`, `POST /api/admin/auth/refresh`, `POST /api/admin/auth/logout`, `GET /api/admin/auth/me` | Staff credentials or staff token | Separate staff sessions. Login requires a verified, enabled editor or admin. |
| `GET/POST /api/admin/opportunities`, `GET/PATCH/DELETE /api/admin/opportunities/{id}` | Editor | Catalogue editing, including drafts, audience, slug, notes and featured rank. Detail includes the last 20 audit entries and a source trace excerpt. |
| `GET /api/admin/opportunities/counts`, `POST /api/admin/opportunities/bulk` | Editor | Editorial counts and bulk publish, archive, hide or review. |
| `POST /api/admin/opportunities/{id}/merge`, `POST /api/admin/opportunities/{id}/reverify` | Editor | Merge a duplicate into another listing and hide it; queue one verification task. |
| `GET /api/admin/opportunities/duplicates`, `POST /api/admin/opportunities/duplicates/dismiss` | Editor | Possible duplicate pairs; mark a pair as different. |
| `GET/PUT /api/admin/organization-aliases`, `DELETE /api/admin/organization-aliases/{alias}` | Editor | Organization names treated as one for the dedupe key. |
| `GET /api/admin/reports`, `PATCH /api/admin/reports/{id}` | Editor | Read reports and mark them resolved. |
| `GET/POST /api/admin/collections`, `PATCH/DELETE /api/admin/collections/{id}` | Editor | Curated items or saved catalogue filters. |
| `GET/PUT /api/admin/site` | Editor | Read and publish versioned homepage content. |
| `GET/POST /api/admin/scans` | Editor | All scans with owner email and traces; start a scan. |
| `GET/PUT /api/admin/settings` | Admin | Publishing defaults, archiving, member scan quotas, sweep interval, crawler and listing checks. |
| `GET /api/admin/users`, `PATCH /api/admin/users/{id}` | Admin | Search users, change roles and disable accounts. Self-demotion and removal of the last active admin are blocked. |
| `GET /api/admin/audit` | Admin | Filter append-only audit entries. |

Existing member paths under `/api/*` remain aliases for one release. The old pending-list and status-moderation routes are removed.

Private calendar feed tokens are stored encrypted, with a SHA-256 hash for lookup. Rotation invalidates the previous URL; disabled accounts' feeds stop working. Links use `PUBLIC_API_URL`, or `APP_BASE_URL` when the web app proxies `/api`.

## Crawler-first scans

The worker crawls enabled sources on their due schedule and when staff request a crawl. Scheduled sweeps (`scans.kind = sweep`) process the crawler pipeline in each category task before their discovery agent. Member scans skip it and work on the member's request (see below), unless no sweep account is configured: then a member's task runs the pipeline after its agent, so crawled candidates still get extracted. Candidates are claimed newest first: by publish date (feed items, or sitemap `lastmod`), then by their source's yield, then by when they were found. The extraction budget defaults to eight pages per category, with at most eighty candidates examined so deterministic rejections do not consume model calls. This budget is separate from the existing opportunity save limits.

Sources can be RSS or Atom feeds, sitemaps, or HTML listings. Migration `0003` seeds seven sources checked live with BlesserBot on 9 November 2026: Wellcome funding schemes, DAAD Ghana funding, NEIP, Grand Challenges grant opportunities, the Tony Elumelu Foundation, Opportunities for Africans RSS and Opportunity Desk RSS. An unreachable Youth feed, a removed Gates Cambridge page and an old redirected Anzisha page were excluded.

Migration `0010_ghana_sources` adds Ghana sources read on 20 November 2026. Enabled: the Ghana Scholarships Authority notices, the University of Ghana research calls, announcements and financial aid pages, KNUST announcements, Africa Research Excellence Fund calls, the Japan embassy notices (MEXT scholarships) and the British Council GREAT Scholarships page for Ghana. Each listed current calls and its robots.txt allowed the listing path, except the Japan embassy, whose robots.txt could not be read; the crawler checks robots.txt before every fetch anyway. Disabled until they post new calls: the Ghana Enterprises Agency expressions of interest and the GETFund scholarship page. Staff enable them from the Sources page. The migration skips any URL staff already added.

### PDF calls

Many government and university calls are only published as PDFs. Listings and feeds keep `.pdf` links as candidates, and the shared page cache reads them for both the pipeline and the agent's `fetch_page`. A response is treated as a PDF when its content type says so, when a generic type comes with a `.pdf` path, or when the body starts with the PDF header and is not labelled HTML.

| Setting | Default | Purpose |
|---|---|---|
| `PDF_MAX_BYTES` | 10,000,000 | Download cap. A larger declared length is refused after one chunk, and a cut file is never parsed. |
| `PDF_MAX_PAGES` | 40 | Pages read per file. |
| `PDF_MAX_CHARS` | 400,000 | Text kept per file, the same as HTML pages. |
| `PDF_TIMEOUT_SECONDS` | 30 | Wall-clock limit; the parser is killed after it. |
| `PDF_MEMORY_MB` | 768 | Address-space limit for the parser. |
| `PDF_CONCURRENCY` | 2 | Parsers running at once per process. |

Text comes from `pypdf` in a separate `python -I` process with memory, CPU-time and no-file-write limits (`opportunities/pdf_text.py`), so a hostile or broken file only costs that child. The page text is the PDF title, its text, and any web links in it, which the extractor can use as the application link. PDF pages never expand into more candidates. Saves from a PDF go through the same grounding checks: the PDF URL is the `source_url`, and the name and full deadline date must appear in its text.

A PDF that is too large, password-protected, unreadable, too slow, or has almost no text (usually a scan) is cached with an error code (`pdf_too_large`, `pdf_encrypted`, `pdf_unreadable`, `pdf_timeout`, `pdf_no_text`). Triage records that code as a rejection instead of retrying it as a temporary fetch failure. Scanned PDFs need OCR, which is not implemented. Word documents are not read either.

The crawler removes navigation and sharing links, normalizes tracking parameters, and records new item URLs only once. Generic funding listings can expand into more candidates without a model call. Triage checks catalogue source URLs, application links, known dedupe keys, content hashes and explicit deadline dates. Publication dates do not count as deadlines. Ambiguous dates and pages with future or rolling application dates survive date triage.

One extraction request returns strict JSON on trimmed page text. It identifies a named open opportunity, its category, regional eligibility and confidence. The same grounding validator handles pipeline and agent saves. Missing required fields, invalid JSON, unsupported names and unsupported deadlines cannot be saved. Results below `EXTRACTION_MIN_CONFIDENCE` default to staff review. Regional exclusions and categories outside the requested scan remain available for later scans that match them.

The database page cache is shared across tasks, workers and scans, including failed fetches. It respects conditional GETs and robots.txt. Repeated fetches of the same window within a task return only a short reminder; a new offset can still read unseen text. Known catalogue and rejected URLs are suppressed before HTTP. Code-confirmed closed URLs become closed candidates. Agent irrelevance is recorded as a rejected outcome scoped to its category and region, so another scope can still consider the page. Domains that produce saves become disabled source proposals, unless the registry already contains that domain.

An agent no longer has to spend turns trying to save something when no useful leads remain. It stops after `DISCOVERY_NO_YIELD_TURNS` without a new save, default five, or `DISCOVERY_MAX_TURNS`, default twelve, and records a Saved/Skipped summary. The global `MAX_AGENT_TURNS` remains an additional ceiling. Explicit staff re-verification can still fetch a known opportunity and refresh its verified deadline.

## Member scans

A member's scan is about that member's request: their focus note, category, region and up to five sites.

1. The agent searches the catalogue first (`search_catalogue`) and records clear fits with `add_catalogue_match`. Fetching a known catalogue URL returns its listing id, so the agent can match it instead of re-saving it.
2. When the member listed sites, the agent reads them next (`fetch_page`), follows links to opportunity pages and saves what fits. Sites must be public http(s) addresses: `scans.service.check_sites` runs the egress guard before the scan starts, and every fetch runs it again, redirects included. A site the crawl rejected earlier is still read when a member asks for it.
3. Then it searches the web.

Every listing a scan returns is a row in `scan_finds`, with `via` (`agent`, `crawler` or `catalog`) and `created` (new to the catalogue). A scan shows all of them, so a scan that finds six fitting listings that already exist shows six, not "added 0". The finished notification says "found N for you, M new to Blesser".

New listings saved from a member's site whose host is not an enabled staff source wait in review (`in_review`, `review_reason = agent_find`) with an editor note naming the site. The member sees them in their scan marked "In review". The site's domain becomes a disabled source proposal, as for any agent save.

### My sources

Members can save up to `MEMBER_SOURCES_MAX` sites (default 10) in "My sources" on the Scans page (`/api/app/sources`). Each has an audience and an optional note on what to look for. Rows live in `member_sources`, private to the member and apart from the staff `sources` registry; the same site can be saved by several members.

The worker's hourly pass checks members whose sources are due (`next_check_at`), up to `MEMBER_SOURCE_CHECKS_PER_HOUR` members per pass (default 20; 0 pauses checks), skipping disabled accounts and members with a check still running. A check is a scan of kind `sources`, one per audience, whose sites are the member's sources and whose focus is their notes. It uses the same agent without web search: catalogue matches, then the member's sites and the pages they link to. Sources are then due again after `MEMBER_SOURCE_CHECK_DAYS` (default 7). "Check now" starts the same check at most once an hour. Source checks never use the member's scan quota, and a check that finds nothing sends no notification.

Finds follow the member-site rule above: new listings wait for staff review unless the site is an enabled staff source. Each saved domain also becomes a disabled staff source proposal through the usual save path, with its save count, so staff can enable strong member sources from the Sources page. A source's `finds` counts the new listings its checks found.

Budgets are separate. The scan's `MAX_OPPORTUNITIES_PER_RUN` counts only the agent's new listings; crawler saves have their own per-task and per-scan limits, so crawled candidates never use up the member's room.

Crawler settings live under `site_settings.crawler` and are editable in admin Settings. Config supplies defaults:

| Setting | Config default | Purpose |
|---|---|---|
| `hours` | `CRAWL_HOURS=6` | Crawl cadence; zero pauses automatic crawls, while explicit crawl requests still run. |
| `max_sources` | `CRAWL_MAX_SOURCES=12` | Sources per pass. |
| `max_items_per_source` | `CRAWL_MAX_ITEMS_PER_SOURCE=40` | Candidate links per source. |
| `max_candidates_per_task` | `CRAWL_MAX_CANDIDATES_PER_TASK=8` | Extraction budget per category. |
| `host_interval_seconds` | `CRAWL_HOST_INTERVAL_SECONDS=2` | Minimum time between host requests, across workers. |
| `page_cache_seconds` | `FETCH_CACHE_SECONDS=21600` | Shared page TTL. |

`EXTRACTION_MAX_CHARS=10000` bounds extraction text and `EXTRACTION_MIN_CONFIDENCE=0.85` sets the review threshold. Temporary page failures retry after 30 minutes. Rejected and closed outcomes remain recorded. A new cycle on a page already in the catalogue is picked up by the scheduled listing checks. A new cycle on a different page is not blocked by the closed listing's key: triage and extraction let it through, and the save reopens the closed listing.

Editors can list, add, edit, enable, disable, delete and request crawls at `/api/admin/sources`. Deleting a source preserves its candidates and opportunities. Every staff write is audited. The Sources page shows candidates and saves, last-crawl yield, errors, failure counts and queued requests.

Scan and task responses add `metrics` without changing existing fields. Metrics distinguish candidates found and considered, extraction attempts and valid extractions, rejection reasons, new saves, model calls, input/output tokens and elapsed task time. `triaged_out` also includes post-extraction decisions such as regional exclusions and failed grounding. Its reasons distinguish these from deterministic rejections.

Run the reviewable probe with `cd api && uv run python -m scripts.scan_pipeline_probe --crawl-only --output ../.agent-logs/crawl.json`, then omit `--crawl-only` for a new three-category scan. It uses the existing enabled account with the earliest creation date and the worker claim/process path. It does not claim other scans. The scan run changes the dev catalogue according to publishing settings.
