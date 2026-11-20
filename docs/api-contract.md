# API contract

The shared contract between the API (`api/`), the public site (`site/`), the member app (`webapp/`) and the admin console (`admin/`). Read `architecture.md` first for the why. Notes on what was removed or migrated describe the move from the first version of the API; that move has shipped. Field names are exact; all JSON is snake_case; dates are ISO 8601 (`YYYY-MM-DD` for dates, UTC datetimes with `Z`).

## Opportunity states

- `status`: `draft` | `in_review` | `published` | `archived` | `hidden`
- `audience`: `public` | `members`
- `review_reason` (nullable): `new_submission` | `agent_find` | `reported` | `source_changed`

Migration from today's values: `pending` → `in_review` (`review_reason = new_submission` for `source = community`, else `agent_find`); `published` → `published` + `audience = public`; `hidden` → `hidden`. Existing rows get a `slug`.

Defaults (stored in `site_settings`, editable in admin):

- `agent_default`: `{"status": "published", "audience": "members"}`. Agent finds go live to members; editors promote them to public.
- `community_default`: `{"status": "in_review"}`.
- `auto_archive`: `true`. The worker archives `published` rows the day after `deadline_date` unless `rolling`, and undated or rolling rows that nothing has confirmed for `freshness.stale_days`.

`OPPORTUNITY_AUTO_PUBLISH` is removed.

## Shapes

```ts
// Public: what anyone may see.
type PublicOpportunity = {
  id: string; slug: string; title: string; organization: string;
  category: string; kind: string; summary: string; eligibility: string;
  benefits: string; location: string; countries: string[]; requirements: string[]; tags: string[];
  deadline: string; deadline_date: string | null; rolling: boolean;
  link: string; source_url: string; verified_at: string | null; published_at: string | null;
  is_open: boolean; days_left: number | null; closed: boolean;   // closed = status archived
}

// Member: public fields plus discovery context.
type MemberOpportunity = PublicOpportunity & {
  audience: "public" | "members";
  found_by: "agent" | "community" | "staff";
  created_at: string;
  is_new: boolean;            // created in the last 7 days
}

// Admin: everything.
type AdminOpportunity = MemberOpportunity & {
  status: Status; review_reason: string | null; editor_note: string;
  featured_rank: number | null; source: string; scan_id: string | null;
  created_by: string | null; published_by: string | null; updated_at: string;
  dedupe_key: string;
  // Scheduled checks: when the source was last looked at and what that found
  // (unchanged, verified, queued, changed, missing, moved, closed, open, unreachable,
  // unconfirmed, reopened, stale), or "" before the first check.
  checked_at: string | null; check_outcome: string;
}

type Page<T> = { items: T[]; total: number };
type Collection = { id: string; slug: string; title: string; intro: string; audience: "public" | "members";
  filter: Record<string, unknown> | null; item_ids: string[]; position: number; published: boolean };
type SiteContent = { hero_title: string; hero_subtitle: string;
  announcement: { text: string; link: string; starts_on: string | null; ends_on: string | null } | null };
type AuditEntry = { id: string; actor_id: string; actor_email: string; action: string;
  entity_type: string; entity_id: string; before: object | null; after: object | null; at: string };
type StaffUser = { id: string; email: string; display_name: string | null; role: "member" | "editor" | "admin";
  email_verified: boolean; disabled: boolean; created_at: string; scans_last_30_days: number };
```

## `/api/public` (no auth)

Only `status = published AND audience = public`, plus `archived` rows by slug (with `closed: true`). Responses send `Cache-Control: public, max-age=60, s-maxage=300, stale-while-revalidate=3600`.

| Method, path | Body / query | Returns |
|---|---|---|
| `GET /opportunities` | `q, category, kind, country, closing_within, include_closed, sort=deadline\|new, limit<=100, offset` | `Page<PublicOpportunity>` |
| `GET /opportunities/{slug}` | | `PublicOpportunity`; 404 if hidden, draft, in review or members-only. An old slug answers `301` to the current one. |
| `GET /opportunities/{slug}/calendar.ics` | | `text/calendar` |
| `GET /facets` | | `{categories, kinds, total, closing_soon}` as today |
| `GET /collections` | | `Collection[]` (published, public) with `items: PublicOpportunity[]` resolved, max 12 each |
| `GET /collections/{slug}` | | one, all items |
| `GET /site` | | `{content: SiteContent, featured: PublicOpportunity[], closing_soon: PublicOpportunity[]}` |
| `GET /sitemap` | | `{opportunities: {slug, updated_at}[], collections: {slug}[]}` |
| `POST /submissions` | `OpportunitySubmit` (as today) + optional `email` | `201 {id}`; rate-limited per IP (5/hour) |
| `POST /opportunities/{slug}/report` | `{reason: string (max 1000), email?: string}` | `202`; rate-limited per IP |

## `/api/app` (member token, `aud = app`)

Every member route that exists today under `/api/*` moves here unchanged (`/api/app/auth/...`, `/api/app/applications`, `/api/app/todos`, `/api/app/scans`, `/api/app/notifications`, `/api/app/calendar/...`). The old `/api/*` paths stay mounted as aliases for one release.

Changes:

- `GET /api/app/opportunities` and `GET /api/app/opportunities/{id_or_slug}` return `MemberOpportunity`: published rows of either audience. New query param `new=true` (last 7 days) and `audience=members|public`. `sort=for_you` orders by the member's match profile and fills `match_score` and `match_terms`; `sort=relevance` ranks search words by match quality.
- `GET`/`PUT`/`DELETE /api/app/match-profile` and `/api/app/saved-searches` (see [Opportunities](opportunities.md#search-and-matching)).
- `GET /api/app/opportunities/facets` counts what members see.
- `POST /api/app/opportunities` (share) lands `in_review`.
- `GET /api/opportunities/pending` and `PATCH /api/opportunities/{id}/status` are removed (moved to admin).
- Register accepts optional `track` (an opportunity slug); after the account is created the opportunity is tracked.

### Applicant kit

These routes exist only under `/api/app` and never expose another member's kit. Extension tokens can read profiles, projects, document lists, storage usage, and downloads. Kit writes and the answer library require an `app` token. Object and linked-ID ownership failures return 404. Admin tokens are rejected. [Applicant kit storage and retention](applicant-kit.md) documents field limits, completeness, encryption, and file storage.

| Method, path | Body or query | Returns |
|---|---|---|
| `GET /profile` | `reveal=1` optional | `Profile`; creates the empty profile on first read with the account email |
| `PUT /profile` | `Profile` writable fields, full replacement; `reveal=1` optional | `Profile`; omitted fields reset to their empty defaults |
| `GET /projects` | | `Project[]` |
| `POST /projects` | `Project` writable fields; name required | `201 Project` |
| `GET /projects/{id}` | | `Project` |
| `PUT /projects/{id}` | `Project` writable fields, full replacement | `Project` |
| `DELETE /projects/{id}` | | `204`; documents and saved answers remain, unlinked |
| `GET /documents` | `kind`, `project_id` optional | `Document[]` |
| `POST /documents` | Multipart `file`, `kind`, `title`, repeated `project_ids[]`, optional `is_default` | `201 Document`; repeated `project_ids` also accepted |
| `PATCH /documents/{id}` | `{title?, kind?, project_ids?, is_default?}`; no null values | `Document` |
| `DELETE /documents/{id}` | | `204`; removes the file and project links |
| `GET /documents/{id}/download` | | Owner-only attachment with `nosniff` and private, no-store caching |
| `GET /documents/usage` | | `{used_bytes: number, limit_bytes: number}` |
| `GET /answers` | `q`, `project_id` optional | `Answer[]`; literal substring search of question and answer, newest first |
| `POST /answers` | `{question, answer, tags?, project_id?}` | `201 Answer` |
| `PUT /answers/{id}` | Same fields, full replacement | `Answer` |
| `DELETE /answers/{id}` | | `204` |

`Profile` and `Project` use the field shapes in [the binding plan, section 2](plans/sharing-and-autofill.md#2-applicant-kit). `completeness`, `created_at`, `updated_at`, `id`, and `word_count` are server-owned where present. Replacement bodies may include those response fields, but the API ignores them. Unknown fields are rejected. Dates use ISO `YYYY-MM-DD`; timestamps use ISO strings.

`Profile` also has `country_of_birth: string` and `place_of_birth: string`, each limited to 200 characters and empty by default. Both contribute to profile completeness. Migration `0006_autofill_v2` backfills empty defaults without replacing existing values.

`Profile.sensitive` contains `{national_id, passport_number, passport_expiry}`. All three values are encrypted at rest. Reads mask all but the final four characters of nonempty values unless `reveal=1`. Clients must fetch revealed values before writing a populated sensitive object back; masked placeholders are rejected. PUT defaults to a masked response too.

```ts
type Document = {
  id: string; kind: "cv" | "cover_letter" | "pitch_deck" | "transcript" |
    "certificate" | "budget" | "financials" | "id_document" | "photo" | "logo" | "other";
  title: string; filename: string; content_type: string; size_bytes: number;
  project_ids: string[]; is_default: boolean; created_at: string;
};
type Answer = {
  id: string; question: string; answer: string; tags: string[];
  project_id: string | null; word_count: number; updated_at: string;
};
```

Uploads accept at most 15 MiB per file and 250 MiB per member. Content inspection allows PDF, DOC, DOCX, PPT, PPTX, XLS, XLSX, CSV, PNG, JPG, and WEBP. The multipart envelope has a 16 MiB ceiling. File or quota overflow returns 413; unsupported content returns 415. Uploads allow 20 calls per hour and 100 per day per member, returning 429 with `Retry-After` when exceeded. One document per kind can be the default; choosing another clears the old default.

Account deletion removes all kit records and files. No kit content is available through admin routes.

### Autofill

`POST /api/app/autofill/fill` accepts an `app` or `ext` token and returns suggestions for review. It never submits a form.

```ts
type FillRequest = {
	page: { url: string; title: string; host: string };
	use: { profile: boolean; project_id: string | null };
	allow_drafting?: boolean; // defaults to true
	fields: {
		key: string;
		tag: "input" | "textarea" | "select" | "contenteditable";
		type: string;
		name: string; id: string; autocomplete: string; label: string;
		placeholder: string; help_text: string; section: string;
		options: { value: string; label: string }[];
		required: boolean; max_length: number | null; word_limit: number | null;
		accept: string;
	}[];
};
type FillResponse = {
	fills: {
		key: string; value: string | string[] | null; document_id: string | null;
		source: "profile" | "project" | "answer" | "document" | "drafted";
		confidence: "high" | "medium" | "low"; note: string; rule: string;
	}[];
	unfilled: { key: string; reason: string }[];
	matched_opportunity_id: string | null;
	usage: { drafted_fields: number; remaining_today: number };
};
```

Matching applies the member's corrections first. It then tries profile and project facts, compatible default documents, saved answers, and one batched model call. Saved answers use normalized-question `pg_trgm` similarity of at least 0.65. Global answers and answers for the selected project qualify. Returned values must fit both limits. Ambiguous options, incompatible documents, unsupported questions, and invalid model values remain unfilled. Unknown model keys are ignored.

The label's head selects an attribute and its qualifier selects the record. Explicit qualifiers take priority over section headings and fieldset legends. For example, `Country of Institution` selects `education.country`, even inside a personal-information section. A qualified attribute absent from the selected record stays empty. Unqualified labels use their section before ordinary synonyms and input hints.

Option matching tries canonical concepts, normalized text, then token similarity. Concepts cover gender, country names and ISO codes and demonyms, degree levels, yes/no wording, employment types, languages, proficiency, months, titles, project stages, and Ghana's 16 regions. Ambiguous concepts and tied options remain unresolved. Consent and declaration controls stay blocked.

Inferences have medium confidence: birth country and citizenship from nationality, nationality from birth country, age from birth date, current employer and role from current experience, highest qualification from education, and full address from its parts. Explicit saved values take priority. `Ghanaian` implies `Ghana` for an empty birth country and carries `rule: "inferred:nationality"`. These suggestions require member review.

Unresolved choices with a known saved fact join the same call as remaining free-text questions. Each choice receives its relevant fact and options with the task `choose_one_option_or_null`. The response must equal an option's value exactly. Labels, invented values, arrays, and other non-string responses are rejected. Checkbox choices return a one-element array. Every model attempt consumes the same daily allowance. Accepted choices use `source: "drafted"`, low confidence, and `rule: "model:choice"`.

Every fill has a rule. Common rules include `concept:gender`, `qualifier:education.country`, `inferred:nationality`, `matched:full_name`, `option:normalized`, `option:tokens`, `document:cv`, `answer:similarity`, `correction`, `model:draft`, and `model:choice`.

Draft context contains only the selected profile and project facts. Sensitive identifiers and passport expiry are excluded, including copies detected in other facts or question metadata. Only exact deterministic matches can return sensitive values. Extension profile reads return empty sensitive fields even with `reveal=1`. Password, payment, consent, declaration, and signature fields remain unfilled. Drafts have low confidence and a review note.

`AUTOFILL_DRAFTS_PER_DAY` defaults to 60 attempts per member per UTC day. Database row locks reserve attempts before the model call, including failures and rejected output. `usage.drafted_fields` counts accepted drafts in this response. `remaining_today` counts unused attempts. Zero disables drafting. `allow_drafting=false` skips model calls and preserves allowance. The route allows 20 calls per minute and 200 per hour per member through the in-process limiter. Excess calls return 429 with `Retry-After`.

Requests allow at most 300 fields, unique nonempty keys of at most 200 characters, and 500 options per field. Strings are trimmed. Labels and help text allow 4,000 characters, most other descriptors allow 500, input types allow 50, and page URLs allow 2,048. Invalid bodies return 422. The ordinary request-body ceiling applies, with overflow returning 413. An unowned project returns 404.

`matched_opportunity_id` is the catalogue opportunity ID from a tracked application whose opportunity `link` or `source_url` matches `page.url`. Matching ignores HTTP versus HTTPS, `www`, fragments, trailing slashes, and common tracking parameters. Other query parameters remain significant. Fill requests and generated answers are not stored by the fill route. Explicit feedback and reports have the separate retention rules below. Responses use private, no-store caching.

### Autofill corrections and reports

```ts
type FillFeedback = {
	page: { url: string; host: string };
	field: FillRequest["fields"][number];
	filled: { value: string | string[] | null; source: string; rule: string | null };
	corrected: { value: string | string[] | null } | { wrong_field: true };
};
type Correction = {
	id: string; host: string; label: string; field_type: string;
	value: string | string[] | null; wrong_field: boolean; updated_at: string;
};
type AutofillReport = {
	page: { url: string; host: string; title: string };
	fields: FillRequest["fields"];
	note: string;
};
```

| Method, path | Auth | Body | Returns |
|---|---|---|---|
| `POST /api/app/autofill/feedback` | `ext` | `FillFeedback` | `204` |
| `GET /api/app/autofill/corrections` | `app` | | `Correction[]`, newest first |
| `DELETE /api/app/autofill/corrections/{id}` | `app` | | `204`, or `404` for an unowned or missing correction |
| `POST /api/app/autofill/reports` | `ext` | `AutofillReport` | `204` |
| `GET /api/admin/autofill-reports?limit=30&offset=0` | Staff, editor or admin | | `{id, page, fields, note, created_at}[]`, newest first |

Corrections belong to one member and use the lowercase URL hostname, normalized label, and lowercase field type as their key. Normalization ignores case, accents, punctuation, and repeated whitespace. Empty labels fall back to placeholder, name, then ID. A hash of the normalized label bounds the database index size. Concurrent updates use an atomic upsert, so the last write wins. A supplied `host` must match the URL hostname, otherwise the API returns 422.

Feedback stores the descriptor and original fill as well as the correction. Original and corrected values are encrypted at rest. They never enter model context. `wrong_field`, null, an empty string, and an empty list suppress all later matching stages for that field. Incompatible options and values over the current field's limits also leave it empty. Corrections cannot override blocked password, payment, consent, declaration, or signature fields. Deleting a correction restores ordinary matching. Staff cannot read corrections.

Feedback values allow 20,000 characters per string and 500 strings per array, within the ordinary request-body ceiling. Feedback and report writes share the autofill throttle. Reports allow 300 field descriptors, a 4,000-character note, and at most 256,000 bytes of serialized validated content. Field descriptors reject an extra `value` property and other unknown properties with 422. Option values are retained because they describe the available choices. Reports contain no original fills or corrections. Staff reads allow `limit` from 1 to 100 and nonnegative `offset`. They follow existing staff report reads, which do not add audit-log entries. Deleting the account cascades corrections and reports.

### Extension authentication

These paths use `/api/app`. Extension access tokens have audience `ext`, the same lifetime as member tokens, and a browser-session ID. Refresh tokens last 90 days, rotate on use, and are stored as hashes.

| Method, path | Auth | Body | Returns |
|---|---|---|---|
| `POST /extension/connect` | `app` | `{name: string}` | `201 {access_token, refresh_token, session: ExtensionSession}` |
| `POST /extension/refresh` | None | `{refresh_token: string}` | `{access_token, refresh_token}` |
| `POST /extension/logout` | `ext` | `{refresh_token: string}` | `204`; revokes the current browser session |
| `GET /extension/me` | `ext` | | `{user: {id, email, display_name}, projects: {id, name, tagline}[], drafting: {enabled, remaining_today}}` |
| `GET /extension/sessions` | `app` | | Active `ExtensionSession[]` |
| `DELETE /extension/sessions/{id}` | `app` | | `204`; owned session only, otherwise 404 |

```ts
type ExtensionSession = {
	id: string; name: string; created_at: string; last_used_at: string | null;
};
```

Names are whitespace-trimmed and must contain 1 through 200 characters. Refresh bodies allow 1 through 512 characters. Connect allows 10 calls per hour per member. Refresh allows 120 calls per minute per IP. Throttle failures return 429 with `Retry-After`. Responses use private, no-store caching.

Every extension request checks session ownership, revocation, and account status in the database. Last-used timestamps update at most once every five minutes, with refresh also updating them. Revocation and logout immediately reject that session's access and refresh tokens. Reusing a rotated refresh token revokes the entire browser session, including the newer pair. Other sessions remain active. Password reset revokes browser sessions. Account deletion cascades them.

The extension audience is accepted only for `POST /autofill/fill`, `POST /autofill/feedback`, `POST /autofill/reports`, `GET /profile`, project list and detail reads, document list, usage and download reads, application list and detail reads, `PATCH /applications/{id}`, and the two extension-only routes above. The patch body must contain exactly `{status: "submitted"}`. Other application patches return 403. All other member routes reject `ext` with 401, including correction list and deletion, kit writes, scans, answers, settings, connect, and session management. Legacy member routes and admin routes also reject extension tokens.

## `/api/admin` (staff token, `aud = admin`)

| Method, path | Role | Body / query | Returns |
|---|---|---|---|
| `POST /auth/login` | — | `{email, password}` | `{access_token, refresh_token, user: StaffUser}`. 403 unless role is `editor`/`admin`, email verified, not disabled. |
| `POST /auth/refresh`, `POST /auth/logout` | — | `{refresh_token}` | as member auth, admin audience; refresh lifetime 12h |
| `GET /auth/me` | editor | | `StaffUser` |
| `GET /opportunities` | editor | `q, status, audience, review_reason, category, kind, source, sort=updated\|deadline\|created, limit, offset` | `Page<AdminOpportunity>` |
| `GET /opportunities/counts` | editor | | `{in_review, members_only, published_public, archived, hidden, draft}` |
| `GET /opportunities/{id}` | editor | | `AdminOpportunity` + `history: AuditEntry[]` (last 20) + `trace_excerpt: string \| null` (the fetched-page excerpt the agent cited) |
| `POST /opportunities` | editor | all editable fields | `AdminOpportunity` (`source = staff`, `status = draft` unless given) |
| `PATCH /opportunities/{id}` | editor | any editable field incl. `status, audience, featured_rank, editor_note, slug` | `AdminOpportunity` |
| `POST /opportunities/bulk` | editor | `{ids: string[], action: "publish_public"\|"publish_members"\|"archive"\|"hide"\|"to_review"}` | `{updated: number}` |
| `GET /opportunities/duplicates` | editor | `limit` (1 to 200, default 50) | `{first, second: AdminOpportunity, score: number, reason: "similar_title"\|"same_page"}[]`, best match first; hidden listings and dismissed pairs excluded |
| `POST /opportunities/duplicates/dismiss` | editor | `{first_id, second_id}` | `204`; the pair stops appearing |
| `GET /organization-aliases` | editor | | `{alias, canonical}[]` |
| `PUT /organization-aliases` | editor | `{alias, canonical}` | `{alias, canonical}`, both normalized; existing listings are re-keyed. 400 when the names match or `canonical` is itself an alias |
| `DELETE /organization-aliases/{alias}` | editor | | `204`; listings are re-keyed |
| `POST /opportunities/{id}/merge` | editor | `{into_id}` | target `AdminOpportunity`; source hidden. Tracking, to-dos, reports, scan results, collection places and crawl candidates move to the target, empty target fields are filled from the source, and the source's slug redirects to the target. 400 when the target is hidden |
| `POST /opportunities/{id}/reverify` | editor | | `202 {scan_id}` |
| `GET /reports` / `PATCH /reports/{id}` | editor | `{resolved: true}` | reports list / one |
| `GET/POST /collections`, `PATCH/DELETE /collections/{id}` | editor | `Collection` fields | `Collection` |
| `GET /site`, `PUT /site` | editor | `SiteContent` | `SiteContent` |
| `GET /settings`, `PUT /settings` | admin | `{agent_default, community_default, auto_archive, member_scan_limits: {per_hour, per_day}, sweep_hours}` | same |
| `GET /scans` | editor | `limit, offset` | all scans, newest first, with owner email |
| `POST /scans` | editor | as member scan | scan |
| `GET /users` | admin | `q, role, limit, offset` | `Page<StaffUser>` |
| `PATCH /users/{id}` | admin | `{role?, disabled?}` | `StaffUser`; cannot demote the last admin or yourself |
| `GET /audit` | admin | `actor_id, entity_type, entity_id, action, limit, offset` | `Page<AuditEntry>` |

Every admin write appends an `audit_log` row in the same transaction (`action` like `opportunity.update`, `opportunity.bulk.publish_public`, `user.role`, `site.update`). Admins never get routes that read members' applications, notes or to-dos.

## Auth details

- Access tokens gain `aud` (`app` or `admin`). Member routes reject `admin` tokens and vice versa.
- `users.role` (`member` default) and `users.disabled_at`. A disabled user's tokens stop working and login fails.
- `OPS_ADMIN_EMAILS` only seeds: on boot, verified accounts with those emails and role `member` become `admin`.
- The front ends keep tokens as the member app does today. The admin console stores its own tokens under its own keys on its own host.

## Dev ports

| App | Dev server | Proxies `/api` to |
|---|---|---|
| API | `:8000` | — |
| Member app | `:5173` | `:8000` |
| Admin console | `:5174` | `:8000` |
| Public site | `:4321` | `:8000` (server-side fetches use `API_INTERNAL_URL`, default `http://localhost:8000`) |

## Scan metrics and sources

Member scan list, start, detail and cancel responses, their legacy aliases, and admin scan responses add `metrics`. Existing fields and task types stay unchanged. Tasks also add `metrics`.

```ts
type ScanMetrics = {
  candidates_found: number; candidates_considered: number;
  extracted: number; saved: number; model_calls: number;
  input_tokens: number; output_tokens: number; duration_seconds: number;
  triaged_out: Record<string, number>;
  sources: Record<string, {seen: number; new: number; error: string}>;
};
// Tasks may additionally expose extraction_attempts, cache_hits,
// pipeline_seconds and pipeline_complete. Metrics for legacy rows are empty.
```

`saved` counts new opportunities, including new finds held in review. `extracted` counts valid extraction responses, including decisions not to save. `model_calls` includes logical provider attempts and agent turns; SDK-level transport retries are not separately counted. Tokens use provider-reported totals. Scan duration sums task durations, including crawler and extraction work, so parallel tasks overlap. A scan with no stored metrics has zero aggregate counters. A standalone scheduled crawl updates source yield counters rather than inventing a scan owner.

`triaged_out` records deterministic reasons such as `url_duplicate`, `dedupe_key`, `content_duplicate`, `deadline_passed`, `navigation`, `empty_page`, `listing_expanded` and `fetch_failed:*`. Post-extraction decisions include `not_relevant`, `region_excluded`, `category_deferred`, `source_mismatch`, `grounding` and `invalid_extraction`. Fetch failures stay queued with a delay. Regional exclusions stay queued for other regions. Agent rejections with `scope:<region>:<category>:` reasons suppress only that scope; confirmed past deadlines can be global closed outcomes.

```ts
type SourceInput = {
  url: string; kind: "rss" | "sitemap" | "listing";
  category_hints: ("startup" | "research" | "student")[];
  enabled: boolean;
};
type Source = SourceInput & {
  id: string; proposed: boolean; last_crawled_at: string | null;
  next_crawl_at: string; crawl_requested: boolean;
  etag: string; last_modified: string; consecutive_failures: number;
  last_error: string; candidates_found: number; opportunities_saved: number;
  last_candidates: number; created_at: string;
};
```

| Method, path | Role | Body | Returns |
|---|---|---|---|
| `GET /api/admin/sources` | editor | | `Source[]`, enabled first |
| `POST /api/admin/sources` | editor | `SourceInput`; category hints default empty and enabled defaults true | `201 Source` |
| `PATCH /api/admin/sources/{id}` | editor | Partial `SourceInput`, no null fields | `Source` |
| `DELETE /api/admin/sources/{id}` | editor | | `204`; candidates and opportunities retained |
| `POST /api/admin/sources/{id}/crawl` | editor | | `202 Source`; queues an enabled source, disabled sources return 400 |

URLs must be public HTTP(S) addresses; normalized duplicates return 409. Source writes append `source.create`, `source.update`, `source.delete` or `source.crawl` audit entries in the same transaction. Agent domain proposals are disabled listings with `proposed=true`; staff decides whether to enable them.

Admin settings add `crawler: {hours, max_sources, max_items_per_source, max_candidates_per_task, host_interval_seconds, page_cache_seconds}`. Omitting `crawler` on an existing settings client preserves its stored values. Bounds are 0 to 8760 hours, 1 to 100 sources, 1 to 200 items per source, 0 to 100 extractions per task, 0.5 to 60 seconds between host requests and 60 to 604800 seconds of page-cache lifetime.

Admin settings also add `freshness: {recheck_days, closing_days, closing_recheck_days, cycle_days, stale_days, max_checks, max_agent_checks}` for scheduled listing checks (defaults 30, 7, 14, 30, 120, 10 and 20). Omitting `freshness` preserves its stored values. Bounds are 1 to 365 days for the recheck and cycle intervals, 0 to 60 days for `closing_days`, 7 to 1095 days for `stale_days`, 0 to 200 pages per pass and 0 to 1000 agent checks a day.
