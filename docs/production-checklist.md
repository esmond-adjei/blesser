# Production checklist

What has been hardened before launch (#34 onward). Open production work, with evidence and a suggested order, is in the [production readiness review](production-readiness-review.md).

## Checklist

| Item | Status |
|---|---|
| Error boundaries | ✅ Page-level (resets on navigation), per settings panel, and app-wide; a crash shows "Try again / Reload page" instead of a blank app |
| Loading / empty / error states | ✅ Shared `LoadingScreen`, `ItemCardSkeleton`, `EmptyState`/`ErrorState` across listings (#44, #48) |
| Query hygiene | ✅ 30 s default `staleTime`; no retries on 4xx, one on 5xx or network errors (`webapp/src/main.tsx`); live views keep their own polling intervals |
| Secrets at rest | ✅ Provider API keys encrypted with Fernet (`api/core/secrets.py`, `SECRETS_KEY` or derived from `AUTH_SECRET`); run `make encrypt-secrets` once after deploying |
| Secrets in transit to the browser | ✅ Keys are never returned (only `has_key`) |
| Logging hygiene | ✅ No secrets, tokens or keys are printed or logged (grep-audited); the worker prints task progress only |
| `AUTH_SECRET` | ⚠️ Must be set in production: without it (and without `SECRETS_KEY`) sessions die on restart and provider keys are stored in plaintext. Startup only warns (review F04) |
| `OPENALEX_MAILTO` | Must be set in every deployment: it puts OpenAlex requests in the polite pool (fewer 429s). The API and worker log a warning at startup when it is empty (#211) |
| Outbound requests (SSRF) | ✅ `fetch_page` and user provider base URLs only reach public http(s) addresses, every redirect hop re-checked, bodies capped (`api/core/egress.py`); private model servers need `ALLOWED_PROVIDER_HOSTS`. Upstream error bodies never reach clients |
| Operator key scoping | ✅ The operator key is only sent to the configured env base URL, never to a user-chosen one |
| CV storage persistence | ✅ `graduator_cv_storage` volume on `api` and `worker`, `CV_STORAGE_DIR` pinned to it (see `docs/deployment.md`) |
| Rate limits, data handling, backups, sandbox | ✅ #56, #59, #65 |
| Monitoring | ⚠️ Usage metering exists (#60); error tracking (e.g. Sentry) is not wired yet. Recommended before launch |
| CSP / security headers | ⚠️ Not set by the app; configure in nginx (`webapp/nginx.conf`) at deploy time |
