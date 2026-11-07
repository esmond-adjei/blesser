# Current working-tree audit, 2026-10-26

Baseline: source at `b4c1b71` (`dev`), with only these audit documents modified locally at publication. The audit began at `41b3ff7`; other work was merged while the review ran. Findings about files that disappeared before completion were excluded, and current source was rechecked before publication. An older 2026-10-15 audit (removed; see git history) described a different revision. The [production readiness review](../production-readiness-review.md) rechecks these findings against later code.

## Scope and method

I mapped the API, worker, database, CV storage, React app, landing site, Compose deployment and CI (about 691 visible files across those areas, including 196 API modules, 214 web-app source files, 29 site source files and 125 API tests). I traced trust boundaries and state transitions, reviewed the prior audit as leads, ran available static/build/test commands and used small local probes for two security gates. This is a risk-based code audit, not a claim that every line or production deployment was exercised. No paid model provider or live product account was used.

Severity: **High** can disclose data or cause material cost when its stated preconditions hold; **Medium** affects security, integrity, privacy, reliability or scale with narrower preconditions; **Low** is a user-facing regression. Confidence says whether the behavior was reproduced locally or inferred from the code. Fixes below are recommendations; this pass changed no application code.

## Summary and order of work

The review found **14 current issues: 4 High, 9 Medium and 1 Low**. The first deployment priorities are to close the database port (F01), prevent assistant tool calls from leaking private records to search (F02), require encryption secrets (F04), and enforce operator-key spending limits even in Beta (F05). Next, address push endpoint validation, auth/session exposure, file and transaction consistency, and CI coverage. Each finding states the condition under which it applies; the audit did not test production firewall rules, push delivery, DNS rebinding or paid model calls.

## Findings

### F01. Postgres is published on every host interface with known default credentials

**High, reproduced in rendered Compose config.** [docker-compose.yml](../../docker-compose.yml) sets `POSTGRES_USER` and `POSTGRES_PASSWORD` to `graduator` by default (lines 18-20), then publishes `${POSTGRES_PORT:-5432}:5432` without a host address (lines 21-22). `docker compose config` showed port 5432 published with no host IP and confirmed that the default password is active in this checkout. Compose therefore binds the database port beyond the internal service network. If the host firewall or cloud network also permits access to that port, those credentials expose the application database, including CV text, chat histories and provider keys. The API's separate loopback bind does not constrain the database port.

**Recommendation:** Do not publish Postgres in the default stack. Put an opt-in loopback-only port under a development profile, require a non-default database password, and verify the rendered Compose configuration before deployment.

### F02. Gradis can send private record contents to a web-search provider without confirmation

**High, reproduced at the decision gate.** [assistant/service.py](../../api/api/assistant/service.py) treats `cv_read` and other record tools as sensitive (lines 153-169), but `_exfiltration_risk` returns immediately for every tool except `fetch_page` (lines 173-179). The model can call `search_web` after reading a CV or draft; the confirm branch at lines 420-448 will not stop it. [assistant/tools.py](../../api/api/assistant/tools.py) forwards the model's query to `web.search_web` (lines 209-218), and [prospects/web.py](../../api/api/prospects/web.py) sends it to the configured search provider (for example, lines 130-138). A local probe with a `cv_read` history and a query containing private text returned `search_web blocked: False`, while the equivalent `fetch_page` call returned `True`.

This requires a bad model decision or prompt injection in material the model reads. The code offers both tools in normal chat modes. **Recommendation:** Treat every outbound tool argument, including search queries, as an egress channel after sensitive reads. Use a deterministic allowlist or explicit confirmation for queries containing private context. Test the full tool loop with an injected page or document.

### F03. A user-controlled push endpoint reaches the worker without an egress guard

**Medium, schema acceptance reproduced; network delivery code-verified.** [notifications/schemas.py](../../api/api/notifications/schemas.py) checks only that the subscription endpoint starts with `https://` (lines 84-96). A local schema probe accepted `https://127.0.0.1:8443/internal`. [notifications/routes.py](../../api/api/notifications/routes.py) stores the supplied endpoint (lines 101-130), and [notifications/push.py](../../api/api/notifications/push.py) passes it to `pywebpush.webpush` (lines 60-71). Normal notification delivery and the test-notification route can attempt an HTTPS connection to the supplied address when VAPID is configured.

Certificate validation and deployment networking determine whether a request reaches an internal service; I did not reproduce delivery to one. **Recommendation:** Accept only known browser push-service origins, or apply a request-time public-address guard that also checks redirects and pins the resolved address. Add a delivery-level test for loopback and private targets.

### F04. Secret storage and the public privacy claim disagree under default configuration

**High, code-verified; conditional on missing secrets.** [core/config.py](../../api/api/core/config.py) defaults both `AUTH_SECRET` and `SECRETS_KEY` to empty (lines 376-383). [core/secrets.py](../../api/api/core/secrets.py) then stores a provider API key as plaintext when both are empty (lines 29-50). Compose makes `api/.env` optional, so this state is deployable. The [public privacy page](../../website/src/pages/privacy.astro) says model keys are encrypted (line 27); [docs/data-handling.md](../data-handling.md) says they are unencrypted (lines 27-29). A warning in logs is the only guard.

**Recommendation:** Fail startup outside an explicit development mode when the persistent encryption/signing secret is absent. Make the privacy copy conditional on the deployment guarantee and update the conflicting internal page. Rotate or encrypt any plaintext keys already stored.

### F05. Default Beta policy removes the stated operator-key spend ceilings

**High, code-verified; conditional on a configured shared model.** [core/config.py](../../api/api/core/config.py) defaults `BILLING_ENFORCED=false`, `ALLOW_SYSTEM_MODEL=true`, and sets daily token/tool ceilings (lines 273-295). [billing/service.py](../../api/api/billing/service.py) maps every account to Beta while billing is off (lines 36-44). Its `daily_ceilings` returns `(0, 0)` for Beta (lines 54-65), and [billing/plans.py](../../api/api/billing/plans.py) gives Beta no quotas and `daily_ceilings=False` (lines 89-98). Model calls require a verified email (billing/service.py:190-197), but verified accounts can spend the operator's model and search keys without these per-account ceilings. Rate limits bound request frequency, not token or money totals.

**Recommendation:** Keep an operator-funded hard ceiling independent of plan billing and include in-flight reservations. Add a deployment-wide budget or kill switch and test Beta with concurrent calls.

### F06. Default mail backend prints live verification and reset links to stderr

**Medium, code-verified; conditional on deploying with the console backend.** [core/config.py](../../api/api/core/config.py) defaults `MAIL_BACKEND` to `console` (lines 231-244). [core/mailer.py](../../api/api/core/mailer.py) prints the entire email body to stderr (lines 49-64). The [password-reset flow](../../api/api/auth/email_flows.py) puts its bearer reset link in that body (lines 78-99). With the Compose defaults, links do not reach users, so they cannot verify an email or reset a password through the expected flow. Anyone with log access can read an unexpired link.

**Recommendation:** Require SMTP or another real delivery backend for a public deployment, and reject console mail outside development. Keep auth links out of production logs.

### F07. Changing a password leaves existing sessions active

**Medium, code-verified.** [auth/service.py](../../api/api/auth/service.py) changes the password hash and commits without revoking refresh tokens (lines 169-180). The code explicitly says sessions stay signed in. A stolen refresh token therefore remains usable after the account owner changes the password, until its normal expiry or logout. **Recommendation:** Revoke every refresh token on password change and consider a per-user session version for existing access tokens.

### F08. The run event stream carries a bearer token in the URL

**Medium, code-verified.** [auth/routes.py](../../api/api/auth/routes.py) accepts `?token=` for SSE (lines 56-71), and [webapp/src/lib/queries.ts](../../webapp/src/lib/queries.ts) constructs an `EventSource` URL containing the access token (lines 442-446). URLs commonly appear in reverse-proxy access logs and diagnostics. An exposed token works until its 15-minute expiry. **Recommendation:** Use a short-lived, single-purpose stream ticket or a fetch-based SSE client that sends the regular Authorization header. Redact query strings in proxy logs meanwhile.

### F09. URL safety check has a DNS time-of-check/time-of-use gap

**Medium, code-verified; exploitability depends on DNS and network controls.** [core/egress.py](../../api/api/core/egress.py) resolves and approves a hostname before the HTTP client connects (lines 56-78 and 90-104), but does not pin the approved address for the connection. Its module comment acknowledges that DNS rebinding between check and connect can reach a private address (lines 13-16). This applies to page fetches and guarded provider requests. **Recommendation:** Enforce egress at a proxy/network boundary or connect to the approved IP while preserving TLS hostname verification; test redirect and DNS-rebinding cases.

### F10. Suggestion acceptance commits document text before committing suggestion state

**Medium, code-verified.** [cv/service.py](../../api/api/cv/service.py) calls `_save_text` during `accept_suggestion` (line 1012). `_save_text` commits immediately (lines 355-374). Only afterward does acceptance mark the suggestion accepted, stale overlapping suggestions, and commit again (lines 1013-1018). A crash or exception between those commits leaves changed document text with the suggestion still pending, and the client can receive an error after the edit was saved. **Recommendation:** Keep the compare-and-set update and all suggestion-state changes in one transaction, then commit once.

### F11. Deleting a document can silently leave its file bytes on disk

**Medium, code-verified.** [cv/service.py](../../api/api/cv/service.py) commits the row deletion before calling `purge_document_files` (lines 547-564). That helper uses `shutil.rmtree(..., ignore_errors=True)` (lines 542-544). A filesystem permission or mount failure leaves personal files behind while the route reports deletion. Account deletion follows the same database-before-files order in [auth/service.py](../../api/api/auth/service.py) (lines 205-222). **Recommendation:** Record durable deletion work and retry it, surface failure to operations, and verify disk removal before promising completed deletion.

### F12. Completed tool actions lost their identifying details in the UI

**Low, reproduced by tests.** [AgentTrace.tsx](../../webapp/src/components/cards/AgentTrace.tsx) renders only `toolActivity(event).label` in a collapsed tool row and group summary (lines 18-40 and 61-89). The corresponding [tests](../../webapp/src/components/cards/AgentTrace.test.tsx) fail because `Searched the web` omits `robotics PhD Ghana` and `Saved programme` omits `Computer Science · University of Ghana` (lines 33-40 and 69-77). People scanning a run cannot tell which search or programme the action represents without opening each row. **Recommendation:** Render the friendly action subject in both collapsed surfaces and keep the tests as the gate.

### F13. List endpoints load large histories and issue avoidable database queries

**Medium, code-verified.** [assistant/conversations.py](../../api/api/assistant/conversations.py) loads every conversation row, including `history_json`, then executes two queries per conversation for its preview and count (lines 66-109). A list of *N* chats therefore needs `1 + 2N` queries and transfers history that the index does not display. [runs/task_service.py](../../api/api/runs/task_service.py) uses `select(ResearchTask)` for task pages and the slim board (lines 149-169), loading the full `log` and `messages_json` columns even though the board does not use them. The SSE code already documents those fields as routinely hundreds of KB per row in [runs/service.py](../../api/api/runs/service.py) (lines 578-583). **Recommendation:** Project only index/board columns, aggregate previews and counts in one query, and fetch traces on the detail path.

### F14. CI does not run the frontend test suite

**Medium, reproduced by local gate.** [.github/workflows/ci.yml](../../.github/workflows/ci.yml) runs oxlint and the Vite build for the web app, but no `npm test`. In this worktree the build and lint pass while `npm test -- --run` fails two of 109 tests, both in AgentTrace. **Recommendation:** Add the existing Vitest command to the frontend CI job and require it for merges.

## Verification and limits

| Check | Result |
|---|---|
| API Ruff lint | Passed |
| Web-app production build | Passed on the final checkout |
| Web-app oxlint | Passed with existing warnings |
| Web-app Vitest | Final run: 107 passed, 2 failed (AgentTrace), across 22 files |
| Website type check and build | Passed |
| `npm audit --omit=dev` in web app and website | Zero reported production dependency advisories at check time; Python dependencies were not advisory-scanned |
| API pytest | Full run: 968 passed, 2 failed, 5 errors; five errors concerned missing database tables or database during setup. Focused rerun: 13 passed, 1 failed; the run-completion cases passed, while the suggestion allowance assertion still failed. |
| Ruff formatting | Failed repository-wide on 190 files; CI explicitly excludes this existing formatting debt |

### Reproduction notes

- Rendered Compose config: `docker compose config --format json` reported `db.ports` as `[{'mode': 'ingress', 'target': 5432, 'published': '5432', 'protocol': 'tcp'}]`, with no `host_ip`. A separate redacted check printed `default_password_active: True`; it did not print the secret value.
- Assistant egress gate: with one user message followed by a `cv_read` tool message, `_exfiltration_risk('search_web', {'query': 'Private CV text'}, history)` returned `False`; `_exfiltration_risk('fetch_page', {'url': 'https://example.org/?d=Private%20CV%20text'}, history)` returned `True`.
- Push endpoint validation: `PushSubscriptionIn(endpoint='https://127.0.0.1:8443/internal', keys={'p256dh':'k','auth':'a'})` accepted the endpoint. This probe made no network request.
- Frontend: `npm run build` passed on `b4c1b71`. `npm test -- --run` then reported `Test Files 1 failed | 21 passed (22)` and `Tests 2 failed | 107 passed (109)`, both failures in `AgentTrace.test.tsx`.
- The first backend test attempt hung before its first case because the sandbox denied socket creation (`PermissionError: [Errno 1] Operation not permitted`). With approved access to local scratch Postgres, the full suite ended at `2 failed, 968 passed, 5 errors`. Five `test_issue13_run_done.py` setup errors reported missing `users` table or missing `graduator_test` database. All run-completion cases passed in a focused rerun, so these five errors were not reproduced; concurrent database recreation is plausible but unconfirmed.
- `test_cv_suggest.py::test_the_token_allowance_gates_suggestions` failed again in the focused rerun: the first suggestion request returned 403 where the test expects 200. The test registers a new account without verifying its email, while `check_model_allowance` refuses operator-key calls from unverified accounts. This appears to be a stale test expectation for the current verification policy. The second full-suite failure, `test_issue13_run_done.py::test_bulk_request_drafts_reopens_done_run`, passed in the focused rerun.

No browser walkthrough, load test, production network probe or paid-provider call was performed. The checkout changed while this review ran; the final frontend build and test run covered `b4c1b71`.

## Rechecked prior-audit blockers that are now addressed in code

The operator key is restricted to the configured system provider/base URL ([providers/service.py](../../api/api/providers/service.py):219-261). Compose mounts a persistent CV storage volume on both API and worker ([docker-compose.yml](../../docker-compose.yml):63-66, 95-98). Ops usage requires a verified allowlisted email ([metering/routes.py](../../api/api/metering/routes.py):27-42). Worker claims use leases and fencing ([runs/queue.py](../../api/api/runs/queue.py):263-364), `save_program` has an account lock and deduplication ([prospects/tools.py](../../api/api/prospects/tools.py):280-318), and request-size middleware runs before route body parsing ([core/body_limit.py](../../api/api/core/body_limit.py)). These are code-level checks, not a production-penetration-test result.
