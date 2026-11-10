# Applicant kit

The applicant kit stores a member's profile, projects, private documents, and reusable answers. Autofill uses selected kit facts to suggest form values and draft answers for review. The [API contract](api-contract.md#applicant-kit) describes the routes.

## Ownership

Routes exist only under `/api/app`. An `app` access token allows kit reads and writes. A session-bound `ext` token allows profile and project reads, document lists, usage, downloads, and autofill. The answer library and all kit writes require `app`. Every object lookup and linked ID checks the member's ownership. Another member receives 404 for reads, writes, downloads, and links to an object they do not own. Admin tokens are rejected. There are no kit routes under `/api/admin`, `/api/public`, or the legacy `/api` prefix.

Profiles, projects, documents, and answers belong to a user through cascading foreign keys. Deleting a project unlinks its documents and clears the project reference on saved answers. The documents and answers remain in the member's library. Deleting a logo document clears the project's logo reference.

## Storage

`DocumentStorage` in `api/applicant_kit/storage.py` defines save, delete, member cleanup, and authenticated download operations. `LocalDocumentStorage` stores files on disk. An object-storage implementation can replace it later.

`UPLOAD_DIR` defaults to `api/uploads`. Relative values resolve under `api/`. Docker mounts the `blesser_applicant_uploads` volume at `/app/uploads` in both the API and worker. The directory must be writable by both processes. Files use generated keys inside a directory derived from the member ID. Original filenames are metadata, never disk paths. New directories have mode 0700 and files have mode 0600.

Multipart parsing spools larger uploads to temporary disk. The storage implementation reads and writes 64 KiB chunks. Files never need to be loaded into memory as a whole. Upload authentication and throttling run before multipart parsing.

Downloads require the owner's member token and send `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, and `Cache-Control: private, no-store`. No upload directory is mounted as a public web directory. JSON kit responses also use private, no-store caching.

## Encryption

The profile's entire `sensitive` object, including passport expiry, is stored as one Fernet-encrypted text column. The profile JSON column contains none of those fields. Fernet uses a SHA-256 key derived from `SECRETS_KEY` with an applicant-kit-specific prefix. Kit encryption does not use the legacy provider-secret plaintext fallback.

`APP_ENV=production` or `APP_ENV=prod` requires both `AUTH_SECRET` and `SECRETS_KEY` when settings load. Missing keys prevent the API and worker from starting. The default environment is `development`.

With no `SECRETS_KEY` in development, the API generates a persistent key in `UPLOAD_DIR/.dev-secrets-key`, with mode 0600. Concurrent processes initialize this file atomically. Restarting with the same directory preserves access to encrypted data. Production never uses this fallback.

Default reads replace all but the final four characters of each nonempty sensitive value with `*`, including the ISO passport-expiry string. `GET /api/app/profile?reveal=1` returns the original values to the owner. PUT accepts plaintext sensitive values and returns masked values unless `reveal=1` is set. Clients must fetch revealed values before saving a full replacement. Mask placeholders are rejected instead of being stored as real identifiers or dates.

Keys must remain stable. Changing or losing the key makes existing sensitive values unreadable. Backups need the database, upload files, and encryption key. Development backups also need `.dev-secrets-key` when no configured key exists. No kit service sends sensitive data to a model.

## Limits

| Item | Limit |
|---|---|
| File | 15 MiB, 15,728,640 bytes |
| Member storage | 250 MiB, 262,144,000 bytes |
| Multipart request | 16 MiB, including headers and metadata |
| Upload throttle | 20 per hour and 100 per day, per member |
| Document formats | PDF, DOC, DOCX, PPT, PPTX, XLS, XLSX, CSV, PNG, JPG, WEBP |
| Name or short field | 200 characters |
| Headline, tagline, address line, publication title | 500 characters |
| Short bio | 300 characters |
| Long bio, project narrative, team bio, custom value | 20,000 characters |
| URL | 2,048 characters, absolute HTTP or HTTPS, no credentials |
| Identifier or monetary amount | 100 or 50 characters, respectively |
| Saved question or answer | 2,000 or 50,000 characters, respectively |

File classification uses libmagic, Office container metadata, and CSV parsing. Filename extensions and client content types do not determine acceptance. Office ZIP files must declare the expected main document type. Macro-enabled Office ZIP formats and generic ZIP archives are rejected. CSV has no binary signature; accepted CSV is UTF-8 structured text with a comma, semicolon, or tab delimiter. Empty files are rejected.

Profile lists allow 30 links, 50 education entries, 50 experience entries, 100 skills, 50 languages, 100 awards, 100 publications, and 30 references. Project lists allow 100 team members, 100 documents, and 100 custom fields. Document links allow 100 projects. Answers allow 30 tags of at most 80 characters.

Dates must be valid ISO dates. Birth and founding dates cannot be in the future. Range ends cannot precede starts. Current experience has no end date. Years range from 1900 to 2200. Project team size is an integer from 1 to 10,000,000 when provided. Money fields are empty or nonnegative finite decimal strings. Currency is empty or three uppercase letters.

Oversized files and exceeded storage quota return 413. Unsupported content returns 415. Invalid fields return 422. The upload throttle returns 429 and `Retry-After`. Throttles use the existing in-process limiter, so multiple API processes do not share throttle counters.

The database locks the member row for kit writes and account deletion. This serializes quota checks, document default changes, and file cleanup across API processes. A partial unique index also enforces at most one default document of each kind per member. Selecting a new default clears the previous one. Unsetting or deleting a default leaves that kind with no default.

## Completeness and search

Completeness is the rounded percentage of populated fields in a fixed list. Empty nested rows do not count. Gender, nationality, pronouns, birth date, and sensitive values do not affect the score.

Profile fields are given name, family name, email, phone, country of birth, place of birth, country of residence, city, headline, short bio, education, experience, skills, and languages. First GET creates an empty profile with the account email, so the initial score is 7. A full replacement can clear the email. The two birth fields are optional strings of at most 200 characters, empty by default. Explicit birth details take priority over autofill inferences.

Project fields are name, tagline, website, sector, country, problem, solution, target customers, business model, traction, team, and use of funds. A project with only a name has a score of 8.

Answer word count is the number of whitespace-separated words. Library search remains a case-insensitive literal substring match over questions and answers. `%` and `_` are literals. Autofill separately uses normalized-question `pg_trgm` similarity, with a minimum score of 0.65 and a GIN index.

## Autofill

`POST /api/app/autofill/fill` accepts page and field descriptors, a profile toggle, an optional owned project ID, and `allow_drafting`, which defaults to true. The [autofill API contract](api-contract.md#autofill) lists the request, response, limits, and errors.

The matcher parses the label's head and qualifier before ordinary synonyms and input hints. `Country of Institution` means the education record's country, and `Email of referee` means the reference's email. Section headings and legends qualify otherwise unqualified labels. An unsupported qualified attribute stays empty instead of falling back to the member's personal field. Explicit labels also take priority over conflicting internal IDs. `api/autofill/vocabulary.py` holds the remaining English synonyms.

`api/autofill/concepts.py` compares gender, countries, degree levels, yes/no wording, employment types, languages, proficiency, months, titles, project stages, and Ghana regions. Country names, ISO codes, and demonyms come from a pinned, vendored dataset. The [data attribution](../api/api/autofill/data/README.md) records its source, license, and regeneration command. Option matching tries concepts before normalized text and token similarity. Thus `Male` matches `Man`, and `Ghanaian` matches `Ghana`. Ambiguous aliases such as `Congolese`, tied options, and repeatable records without a clear index remain unfilled.

The engine derives birth country and citizenship from nationality, nationality from birth country, age from birth date, current role and employer from current experience, highest qualification from education, and full address from its parts. Inferences have medium confidence and an `inferred:` rule. For example, nationality `Ghanaian` supplies `Ghana` for an empty birth country with `rule: "inferred:nationality"`. Explicit saved values take priority. Members must review inferences because nationality does not establish birthplace.

File inputs use the default document of the detected kind and respect `accept`. Only unlinked profile documents and documents linked to the selected project qualify. Saved answers match global questions or questions for the selected project. Oversized facts and answers are skipped instead of truncated.

Remaining free-text questions and unresolved choices with a known fact go to the configured provider from `api/agent/llm/factory.py` in one batched call. Each choice supplies its relevant fact and available options as `choose_one_option_or_null`. The API accepts only an exact option value, with a one-element array for a checkbox. Choices without facts stay empty. The rules require JSON, restrict answers to supplied facts, prohibit invented numbers, names, and dates, and request null when facts are insufficient. The API discards unknown keys, non-string values, truncated output, tool calls, values beyond either limit, and sensitive values. Accepted drafts and model choices have low confidence and a review note. Every fill carries a `rule`, including deterministic facts, documents, saved answers, corrections, and model output. Members review and submit their own forms.

Sensitive values fill only fields identified as that exact national-ID, passport-number, or passport-expiry field. They never enter model context. Copies detected in other facts and question metadata are removed too. Extension profile reads return empty sensitive fields even with `reveal=1`. Passwords, payment fields, consent, declarations, and signatures are never filled.

`AUTOFILL_DRAFTS_PER_DAY=60` limits attempts per member per UTC day. Zero disables drafting. The database reserves allowance before a model call and serializes concurrent requests. Failed calls and rejected answers still count. The response reports accepted drafts for the request and unused daily attempts. `allow_drafting=false` consumes no allowance. Autofill allows 20 requests per minute and 200 per hour per member through the existing in-process limiter.

The response matches the page URL against opportunity links and source URLs in the member's application tracker. Scheme, `www`, trailing slashes, fragments, and common tracking noise are ignored. Meaningful query parameters remain significant. The returned ID identifies the catalogue opportunity. The fill route stores only daily usage. Members explicitly opt into storage through feedback or problem reports.

`POST /api/app/autofill/feedback` requires an extension token and stores a member's descriptor, original fill, and correction. The engine applies corrections before other matching, keyed by member, URL hostname, normalized label, and field type. An atomic upsert makes the latest write win. Original and corrected values are encrypted at rest and excluded from model context. Empty corrections and `wrong_field` suppress later matching. Invalid choices and oversized corrected values also stay empty. Blocked controls remain blocked.

`GET /api/app/autofill/corrections` requires an app token and returns the member's corrections, newest first. `DELETE /api/app/autofill/corrections/{id}` removes an owned correction and restores ordinary matching. Other members and staff cannot read or delete these records.

`POST /api/app/autofill/reports` requires an extension token and stores page metadata, field descriptors, and the member's note. Descriptors reject actual `value` properties. Option values remain part of their descriptors. Reports are capped at 300 fields, a 4,000-character note, and 256,000 serialized bytes. Editors and admins read reports through the paginated `GET /api/admin/autofill-reports` route. This follows the existing staff report-read pattern without a new audit entry. Both write routes share the autofill throttle. The [API contract](api-contract.md#autofill-corrections-and-reports) gives all shapes and errors.

Browser connections use `ext` access tokens and rotating 90-day refresh tokens tied to `auth_extension_sessions`. Session checks run on every request. Logout, revocation from Connected browsers, refresh-token reuse, and password reset invalidate that session's access and refresh tokens. The [extension auth contract](api-contract.md#extension-authentication) lists the routes and audience boundaries.

Run `uv run python -m scripts.measure_autofill` from `api/` to measure deterministic coverage, correct and incorrect fills, and counts per rule. Fixtures include the original synthetic forms, the owner's v2 failures, and descriptors fetched from six public Google Forms, Greenhouse, Lever, and grant forms. Each public fixture records the source URL, fetch timestamp, and response hash. Expected values use the synthetic applicant kit. `uv run python -m scripts.harvest_autofill_forms` refreshes descriptors into `/tmp/autofill-public-descriptors` for review. It performs public GET requests and never submits forms. Harvested fixtures may omit controls rendered only by client-side JavaScript.

The measurement makes no model calls by default. Add `--real-draft` to check the configured Ollama endpoint and measure one batched Siwa drafting call with provider-reported token use. The script makes no database writes. Corpus accuracy measures these labeled fixtures only, not production-wide accuracy.

Migration `0005_autofill` enables `pg_trgm`, backfills normalized questions, adds their trigram index, and adds browser sessions and daily draft usage. Refresh grants gain a browser-session reference and a used timestamp for replay detection. Downgrade removes these additions but leaves the shared `pg_trgm` extension installed.

Migration `0006_autofill_v2` adds correction and report tables with account-deletion cascades. It backfills birth-country and birthplace defaults into profile JSON while preserving existing values. Downgrade removes both tables and both profile keys.

## Retention and deletion

Kit content remains until the member deletes it or deletes their account. Corrections remain until deleted individually or with the account. Reports remain until account deletion. There is no automatic expiry. Documents are independent of projects and can link to several projects.

Successful account deletion removes the member's whole file directory, including unreferenced files, and cascades all kit database rows and document links. Other members' files remain. Failed confirmation leaves the kit intact. Filesystem cleanup happens under the member lock before database deletion commits. Cleanup failure aborts account deletion, and cleanup can be retried.

Ordinary upload failures remove partial files. A process or host crash between file creation and the database commit can leave an unreferenced file until account cleanup. A crash during deletion can leave metadata for a file already removed. These operations span Postgres and disk without a distributed transaction. Backup copies follow the deployment's separate backup-retention policy.

Migration `0004_applicant_kit` adds five tables: `applicant_profiles`, `applicant_projects`, `applicant_documents`, `applicant_document_projects`, and `applicant_answers`. Downgrading removes those tables. Alembic never removes disk files; operators must handle upload-volume retention separately when rolling back the feature.
