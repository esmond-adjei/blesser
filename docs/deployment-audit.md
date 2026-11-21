# Blesser deployment audit

Audit date: 2026-11-21. Baseline: `247893c791477ac16424e5356db9cd41cfe2bd3f`. The local source branch was `main`; deployment work now lives on local `deploy`.

Existing changes in admin, member UI and illustration assets were present before the audit and remain uncommitted. No server, DNS, firewall, credential, or provider settings were changed. See [the implementation plan](deployment-plan.md) and [action log](deployment-actions.tsv).

Status: deployment is not approved or verified.

## Runtime and storage inventory

| Component | Current requirement | Deployment implication |
| --- | --- | --- |
| API | Python 3.12, FastAPI, asyncpg, Uvicorn | Internal port 8000, shared backend image with worker. |
| Worker | `python -m api.worker`, default concurrency 4 | PostgreSQL queue and heartbeat, scans, crawling and notifications. Must wait for migrations. |
| Database | PostgreSQL 16 | Named volume `blesser_pgdata`. No Redis or separate broker required by the current Compose stack. |
| Member app | Node 26 build, Vite, Nginx | Root npm workspace context and `design-system`; container port 80. |
| Admin | Separate Node 26 build and Nginx | Separate domain and backend access controls; container port 80. |
| Public site | Astro Node standalone server on 4321 | Server-rendered runtime needs internal API URL and public app and site origins. |
| Public edge | Nginx, `ops/nginx/site.conf` | Routes public pages to site and `/api` to backend. Keep equivalent routes if replacing it. |
| Applicant files | Shared API and worker `/app/uploads` | `blesser_applicant_uploads` contains persistent documents and previews. It is required in backups. |
| File processing | libmagic, olefile, Pillow, pypdfium2, pypdf | Validate PDF and image preview generation on native ARM64 and AMD64. |
| Browser extension | Separate npm workspace | Distributed client artifact, not a server daemon. Public API host, HTTPS and extension authorization boundary need smoke tests. |

The public site also has a scheduled GitHub Pages static build. Choose one canonical production destination. Default plan moves its server version to Coolify and disables conflicting Pages publication only after approval.

## Environment and external dependencies

The source of truth is `api/api/core/config.py`, with names documented in `api/.env.example`. Set explicit production values instead of importing local `.env` files.

| Purpose | Settings and handling |
| --- | --- |
| Core security | `APP_ENV=production`, stable `AUTH_SECRET`, stable `SECRETS_KEY`, strong PostgreSQL password, exact `CORS_ORIGINS` |
| Data and capacity | `DATABASE_URL`, `UPLOAD_DIR=/app/uploads`, database pool sizes, worker concurrency and PDF parsing limits |
| Mail and identity | SMTP backend and connection settings, `MAIL_FROM`, `APP_BASE_URL`, `PUBLIC_API_URL`, `SITE_URL`, `OPS_ADMIN_EMAILS` |
| Research | `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, optional `LLM_BASE_URL`; search provider keys through configured search settings. Verify actual enabled adapters, not stale prose. |
| Scheduled work | Opportunity sweep email and interval, crawler limits, notification delivery settings |
| Optional identity and push | Google OAuth client and secret with exact callback URLs; stable VAPID keys and subject |
| Member build | `VITE_API_URL` empty for same-origin, `VITE_SITE_URL` points to the public site |
| Public site runtime | `API_INTERNAL_URL=http://api:8000`, public `PUBLIC_APP_URL`, `SITE_URL`, optional `CONTACT_EMAIL` |

Preserve original encryption keys. In development, `api/api/applicant_kit/encryption.py` may create `.dev-secrets-key` under uploads. If existing data used that fallback, changing to a new production key requires a tested data re-encryption procedure. Preserve the original fallback securely for migration rather than silently replacing it. Do not commit it.

Outbound HTTPS, DNS and SMTP are required for the corresponding features. Hosted model and search APIs are the initial plan. Running a local model is outside the current capacity and budget proposal.

## Findings

Severity describes deployment impact. Confirmed means observed in current source, not reproduced on a server.

| ID | Severity | Confidence | Evidence and impact | Required resolution |
| --- | --- | --- | --- | --- |
| B1 | High | Confirmed | `docker-compose.yml:18-21` supplies default DB credentials and publishes PostgreSQL on every host interface. | Require a unique password and remove published DB ports from production. Do not rely on UFW alone for Docker-published ports. |
| B2 | High | Confirmed | Compose does not force `APP_ENV=production`. Settings default to development and console mail. Production secret validation can be bypassed by this omission. | Explicit production environment, stable keys, SMTP, exact public URLs and admin bootstrap. Verify startup fails on missing required values. |
| B3 | High | Confirmed | `ops/backup.sh` only dumps Postgres. `docs/backups.md` and `docs/deployment.md` incorrectly state everything is in Postgres. Compose mounts `blesser_applicant_uploads`. | Back up DB, uploads and necessary key material as a consistent encrypted recovery set. Correct docs before launch. |
| B4 | High | Confirmed mismatch | `api/api/applicant_kit/storage.py:21-23` allows 15 MB files and 16 MB upload requests. All three Nginx proxies cap API bodies at 2 MB. | Set an upload-route limit that admits the intended file plus multipart overhead and test allowed and rejected boundaries. |
| B5 | High | Confirmed gap | Worker waits for DB health only. API applies migrations at startup in `api/api/core/db.py:63`; Alembic has no migration advisory lock in `api/alembic/env.py`. | One migration job, concurrency protection, schema readiness before API and worker execution. Test redeploying with pending work. |
| B6 | High | Confirmed gap | No production or Coolify Compose, image publishing workflow, or cross-architecture build gate. CI only runs automatically on `main`, `develop` and PRs. | Add `deploy` release flow, explicit Coolify variables, immutable multi-architecture images, health and restore gates. |
| B7 | High if reproduced | Suspected build blockers | API runs editable-project `uv sync` before source copy. Frontend Dockerfiles copy inconsistent subsets of the five workspace manifests before `npm ci`; even the webapp omits `extension/package.json`. | Test fresh builds without local caches. Fix source/install order if needed and copy the complete required workspace metadata. Missing manifests are an observed discrepancy, not a reproduced npm failure. |
| B8 | Medium | Confirmed gap | API and DB have checks; member app, admin, site, edge and worker do not. Worker heartbeat exists in `api/api/scans/queue.py`. | Route-specific HTTP checks, SSR-to-API smoke test, per-worker heartbeat and real queued task test. |
| B9 | Medium | Confirmed behavior, impact needs testing | Proxies overwrite external scheme with internal `$scheme`; API command does not explicitly configure proxy trust. Member webapp has no streaming-specific proxy configuration. | Test trusted client IP, HTTPS links and long requests. Add streaming handling where actual routes require it. |
| B10 | Medium | Confirmed gap | Floating base images and `uv:latest`, root backend runtime, no resource or log limits. Root `.dockerignore` excludes `api/.env`, but not every environment-file name. | Pin and scan images, restrict build contexts, run with reviewed least privilege and upload ownership, limit logs and resource use. |
| B11 | High | Confirmed verification gap | `ops/restore-verify.sh:22-23` only requires a nonempty revision and one user. It never compares expected revision, source counts, uploaded bytes or encrypted-field readability. | Restore isolated DB and uploads, assert exact expected values, login, decrypt fixture fields and download a fixture document. |

## Verification record

- All three existing deployment configuration test functions passed when executed directly with `runpy`, without the suite's database fixtures.
- `bash -n` passed for backup and restore verification scripts.
- Selected native dependencies in `api/uv.lock` have ARM64 wheel candidates including pypdfium2, Pillow, cryptography, lxml and asyncpg. This does not establish complete ARM compatibility.
- Local Node is 24.13.0; Blesser's declared engine is Node 26 or later. Host builds with the current Node would not reproduce the requested container runtime.
- Docker daemon access was denied. No clean image builds, running health checks, backup restores, application migrations or server benchmarks ran.
- Git tracks example environment templates in the checked environment-file paths. Existing ignored local environments were not read. No full history secret scan or remote GitHub review was performed.

This is a source-based deployment readiness audit. It does not certify application security or the existing UI changes.
