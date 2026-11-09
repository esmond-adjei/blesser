# Applicant kit

The applicant kit stores a member's profile, projects, private documents, and reusable answers. Phase 2 has no model calls or autofill routes. The [API contract](api-contract.md#applicant-kit) describes the member routes.

## Ownership

Routes exist only under `/api/app` and require an `app` access token. Every object lookup and linked ID checks the member's ownership. Another member receives 404 for reads, writes, downloads, and links to an object they do not own. Admin tokens are rejected. There are no kit routes under `/api/admin`, `/api/public`, or the legacy `/api` prefix.

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

Completeness is the rounded percentage of populated fields in a fixed list. Empty nested rows do not count. Optional demographic and sensitive values do not affect the score.

Profile fields are given name, family name, email, phone, country of residence, city, headline, short bio, education, experience, skills, and languages. First GET creates an empty profile with the account email, so the initial score is 8. A full replacement can clear the email.

Project fields are name, tagline, website, sector, country, problem, solution, target customers, business model, traction, team, and use of funds. A project with only a name has a score of 8.

Answer word count is the number of whitespace-separated words. Search is a case-insensitive literal substring match over questions and answers. `%` and `_` in search text are literals. Phase 2 does not use `pg_trgm` or similarity matching.

## Retention and deletion

Kit content remains until the member deletes it or deletes their account. There is no automatic expiry. Documents are independent of projects and can link to several projects.

Successful account deletion removes the member's whole file directory, including unreferenced files, and cascades all kit database rows and document links. Other members' files remain. Failed confirmation leaves the kit intact. Filesystem cleanup happens under the member lock before database deletion commits. Cleanup failure aborts account deletion, and cleanup can be retried.

Ordinary upload failures remove partial files. A process or host crash between file creation and the database commit can leave an unreferenced file until account cleanup. A crash during deletion can leave metadata for a file already removed. These operations span Postgres and disk without a distributed transaction. Backup copies follow the deployment's separate backup-retention policy.

Migration `0004_applicant_kit` adds five tables: `applicant_profiles`, `applicant_projects`, `applicant_documents`, `applicant_document_projects`, and `applicant_answers`. Downgrading removes those tables. Alembic never removes disk files; operators must handle upload-volume retention separately when rolling back the feature.
