# Production readiness review, 2026-10-26

Baseline: `dev` at `77f820f` (1.0.0 plus five commits), reviewed on branch `docs/production-review`.

This review asks one question: what has to change before Graduator can run in production for many users at once, with more than one API or worker process? It builds on the [2026-10-25 working-tree audit](audit/02-current-worktree-report.md) and does not repeat that audit's evidence. Section 1 rechecks the earlier findings against today's code. Section 2 lists new findings, which are mostly about scaling and architecture, the areas the earlier audits covered least. Section 3 puts everything in a suggested order.

**Method.** I read the code and traced it end to end on the paths that carry load: the worker queue, the run event stream, Gradis streaming, the database pool, rate limits, housekeeping, deployment and the frontend's polling. Nothing was load-tested. Where a finding depends on behaviour under load, it says so and names the measurement that would confirm it.

**Severity:** P0 blocks launch · P1 fix before a public launch · P2 fix before scaling past one process or a few hundred active users · P3 polish.

---

## 1. Status of the 2026-10-25 findings

| ID | Finding | Status today | Evidence |
|---|---|---|---|
| F01 | Postgres published on every interface with default credentials | **Open** | `docker-compose.yml:22` still publishes `${POSTGRES_PORT:-5432}:5432` with no host IP; password default unchanged |
| F02 | Gradis can send private record contents to web search without confirmation | **Open** | `assistant/service.py:191` still returns `False` for every tool except `fetch_page` |
| F03 | User-controlled push endpoint reaches the worker without an egress guard | **Open** | `notifications/schemas.py:91-95` checks only the `https://` prefix |
| F04 | Secrets fall back to plaintext under default config | **Open** | `core/config.py:380,383` default `auth_secret` and `secrets_key` to `""`; startup only warns |
| F05 | Beta plan removes the operator-key spend ceilings | **Open** | `billing/service.py:52-63` exempts Beta; `billing/plans.py:95-96` sets `quotas={}` and `daily_ceilings=False` |
| F06 | Console mail backend prints reset links to stderr | **Open** | `core/config.py:234` still defaults `mail_backend = "console"` |
| F07 | Changing a password leaves sessions active | **Open** | `auth/service.py:169-180` does not revoke refresh tokens |
| F08 | Run event stream sends the bearer token in the URL | **Open** | `webapp/src/lib/queries.ts:440-444` |
| F09 | Egress check has a DNS time-of-check/time-of-use gap | **Open** | `core/egress.py` still checks the address and connects separately |
| F10 | Accepting a suggestion saves the text in one commit and the suggestion state in another | **Open** | `cv/service.py:1012` still calls `_save_text`, which commits on its own |
| F11 | Deleting a document can leave its files on disk | Not rechecked | No commits have touched this code path since the audit |
| F12 | Collapsed tool rows lost their subject; two tests fail | **Open** | `AgentTrace.test.tsx` still fails 2 tests on `dev` |
| F13 | List endpoints load full histories and run N+1 queries | **Open** | `assistant/conversations.py:92-109` still runs a count query per conversation |
| F14 | CI does not run the frontend tests | **Open** | `.github/workflows/ci.yml` runs only lint and build for `webapp` |

None of the 14 has been fixed since the audit. The earlier audit's "addressed in code" list (operator key scoping, CV volume, task leases, `save_program` locking, the body-size middleware) still holds.

---

## 2. New findings

### Database connections and transactions

#### N1 · P1 · A Gradis turn holds a database connection for the whole turn, idle in a transaction during the model call

`begin_streaming_turn` and `resume_streaming_turn` (`assistant/service.py:582`, `:680`) open one session and keep it for the entire turn, yielding SSE frames to the client from inside `async with SessionLocal()`. In `_run_streaming_loop`, `queue.take_urgent` runs a `SELECT` at the top of every model turn (`assistant/service.py:279`). When nothing urgent is queued, nothing commits before `provider.chat_stream(...)`. The connection then sits *idle in transaction* for the whole model stream, often tens of seconds, and stays checked out between turns too.

The worker's orchestrator avoids exactly this: it commits before each model call (`agent/orchestrator.py:502-508`, with a comment explaining why). Gradis never received the same fix.

Consequences:

- The API pool holds `db_pool_size + db_max_overflow` = 20 connections by default, so about 20 concurrent Gradis turns take all of them. Every other request then waits on `pool_timeout` (30 s) and fails with a 500.
- Long idle-in-transaction sessions hold back vacuum on the tables they read.
- A client that disconnects mid-stream raises `CancelledError` inside the session's `__aexit__`. That is the likely source of the `SAWarning: The garbage collector is trying to clean up non-checked-in connection` seen in development. The runs feed has a comment documenting this same failure (`runs/service.py:874-878`).

**Fix:** use short sessions per step: load the conversation, close the session, stream from the model with no session open, then open a new session to persist the result. At minimum, `await session.commit()` before every `chat_stream` call. Add a test that asserts no transaction is open while the provider is streaming.

#### N2 · P1 · The run event stream uses one Postgres connection per open tab, and hangs once the cap is reached

Every SSE stream opens its own `asyncpg.connect(listener_dsn())` outside the pool to `LISTEN` (`runs/service.py:853`). A process-wide semaphore caps streams at `sse_max_streams` = 32 (`core/config.py:345`). The semaphore is acquired *before* the first byte is sent (`runs/service.py:850-851`), so the 33rd viewer gets an open HTTP request that never responds. It gets no 503 and no `retry:` frame, and the browser just shows a page that never goes live.

Every stream also receives every `NOTIFY` on the shared channel and filters it in Python. One tool call in any run therefore wakes every open stream on every API process.

Two things make this worse:

- The candidate page now opens a stream while a draft is being written (`webapp/src/pages/CandidateDetail.tsx`, added in `8dff364`).
- Several tabs of the same run each take a slot.

**Fix:** run one `LISTEN` connection per API process and pass events to subscribers in memory, keyed by `run_id`. Stream count is then bounded by memory, not Postgres connections. Until then, try to acquire a slot without waiting and return `503` with `Retry-After` when none is free.

#### N3 · P2 · No database timeouts anywhere

There is no `statement_timeout`, no `idle_in_transaction_session_timeout`, no asyncpg `command_timeout` and no `pool_recycle` (`core/db.py`). One slow query or one leaked transaction (see N1) can hold a connection indefinitely. Behind a load balancer or PgBouncer that drops idle connections, `pool_pre_ping` covers stale sockets but not hung ones.

**Fix:** set connection `server_settings` on the engine:

- `statement_timeout` around 30 s for the API and longer for the worker.
- `idle_in_transaction_session_timeout` around 60 s.

Also set `pool_timeout` deliberately, and log pool exhaustion.

### Write amplification in the trace and checkpoint

#### N4 · P1 · Each task's trace and checkpoint are rewritten in full on every step, and the feed re-parses them on every wake

- `_make_event_sink` keeps the task's whole event list in memory and writes `task.log = json.dumps(events)` after every tool call and every turn (`runs/queue.py:184`, `:194`).
- `on_checkpoint` writes the whole `messages_json` every turn (`runs/queue.py:600`). The run feed itself documents this column as "routinely hundreds of KB per row".
- Over a task's life, the bytes written to the database therefore grow with the square of the trace length. Each rewrite also creates a new TOAST copy and its WAL.
- On the read side, every stream that sees `log` change re-selects the full `log` text and runs `json.loads` on all of it, just to send the new tail (`runs/service.py:718-727`). That happens per wake, per stream.

At the default concurrency of 8 to 16 tasks per worker, this is the main source of database I/O and WAL volume. It also makes the feed's CPU cost grow with the number of viewers.

**Fix:** make the trace append-only. `tool_call_logs` already stores one row per call. Add a per-task sequence number to it, write turn notes there too, and have the feed send rows with `seq > last_sent`. Then `research_tasks.log` stops being written on every step. For checkpoints, store the messages appended since the last checkpoint, or only checkpoint every N turns.

### State that only works with a single process

#### N5 · P1 · Throttles and the one-turn-per-chat guard live in process memory

| State | Where | What breaks with two API processes |
|---|---|---|
| Per-account rate limits | `core/ratelimit.py:59` (`RateLimiter`) | Each process counts separately, so limits are multiplied by the number of processes |
| Login lockout | `auth/security.py:102` (`_attempts`) | Brute-force allowance is multiplied by the number of processes |
| One Gradis turn per conversation | `assistant/service.py:40` (`_RUNNING_TURNS`) | Two turns can run on one chat and overwrite each other's history |
| SSE cap | `runs/service.py:566` | Each process allows its own 32 streams |

The module docstrings admit the single-process assumption, but nothing enforces it. Adding `--workers 2` to uvicorn, or a second replica, silently weakens every one of these.

The `_RUNNING_TURNS` guard also has a race inside a single process. `chat_stream` checks `turn_running()` in the route (`assistant/routes.py:265`), but the conversation is only added to the set once the response body starts streaming (`assistant/service.py:642`). Two requests sent close together both pass the check.

Neither dict is ever pruned. The `reset_email` bucket is keyed by whatever email address the caller submits, so an anonymous caller can grow the API's memory without bound.

**Fix:** move the per-turn guard to the database: a conditional `UPDATE … SET turn_started_at = now() WHERE turn_started_at IS NULL OR turn_started_at < now() - interval …` on the conversation row, or an advisory lock taken in the route. Move rate limits and the login lockout to Postgres (a small counters table, or advisory locks) or to Redis. Until then, document and enforce one API process, for example with a startup check.

#### N6 · P1 · Behind nginx, every request appears to come from nginx, so the per-IP reset limit throttles all users at once

uvicorn trusts `X-Forwarded-For` only from `--forwarded-allow-ips`, which defaults to `127.0.0.1`. In Compose, nginx reaches the API from the webapp container's address on the Docker network, so the header is ignored and `request.client.host` is nginx. The password-reset limit is keyed by that address (`auth/routes.py:186`): `reset_ip` allows 10 per 15 minutes and 50 per day. Under this config, that becomes a single sitewide limit. After 10 reset requests from any users, nobody can request a reset for the rest of the window.

Any future per-IP control, and the IP addresses in logs, are wrong in the same way.

**Fix:** start uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy network or address>` in `api/Dockerfile` and Compose. Then check that `request.client.host` is the browser's address when the request goes through nginx.

### Worker housekeeping when the worker is scaled

#### N7 · P2 · Every worker process runs every housekeeping job, and digest emails are not idempotent

`main_loop` starts `reaper_loop` in every worker (`runs/queue.py:857`), and the compose file documents `--scale worker=3`. `send_digests` (`notifications/deadlines.py:100-160`) has three problems:

- It reads all the preference rows, sends each email, and commits `last_digest_on` once at the end. Two workers on the same hour both send every digest.
- One SMTP exception aborts the loop before the commit. The users already emailed get the digest again the next hour, and the users after the failure get nothing.
- Emails go out one by one inside the reaper loop. While a large digest batch runs, the loop is not requeueing stale tasks or pruning heartbeats.

`check_deadlines`, `prune_traces` and `sweep_expired_exports` also run in every worker. They look idempotent, but each is duplicated work, and the deletes are unbatched.

**Fix:** run housekeeping in one worker only, chosen with `pg_try_advisory_lock`. For digests, claim each user's digest before sending: a conditional `UPDATE … SET last_digest_on = :day WHERE last_digest_on IS DISTINCT FROM :day RETURNING`, committed per user. Move digest sending out of the reaper loop.

#### N8 · P2 · Migrations run when the API boots, with no lock and no ordering against the worker

`init_db` runs `alembic upgrade head` in the API's startup (`core/db.py:57-68`, `main.py:48`). Alembic takes no lock (`alembic/env.py`), so two API replicas starting together race on the same migration. The worker never migrates and does not wait for the API to finish. A new worker image can start against the old schema, and an old worker can keep running against the new one.

The earlier audit's O2 described the deploy-ordering half of this. It is still open.

**Fix:** run migrations as a separate one-off Compose service that `api` and `worker` both depend on with `service_completed_successfully`. Take `pg_advisory_lock` in `env.py` as well. Add a schema-version check to the worker's startup.

### Outbound HTTP and model clients

#### N9 · P2 · A new model SDK client is created for every task and chat turn, and never closed

`get_provider(...)` builds a new provider object for each task and each Gradis turn (9 call sites). Each object lazily creates its own `anthropic.AsyncAnthropic` or `AsyncOpenAI` client (`agent/llm/anthropic_provider.py:113`, `openai_compat_provider.py:188-191`). The guarded OpenAI-compatible path also creates its own `httpx.AsyncClient`. None of them is ever closed: there is no `aclose()` anywhere in `agent/`.

As a result:

- Every task pays a new TLS handshake.
- No keep-alive connection is reused across tasks.
- Sockets stay open until garbage collection, so file-descriptor use rises with throughput.

The search, fetch and OpenAlex clients are already shared per process (`prospects/web.py:54-67`, `openalex.py:61`), so this is the exception.

**Fix:** cache clients per process, keyed by provider, base URL and a hash of the key, and close them on shutdown. Keep a per-call client only for one-off connection tests.

### Queue throughput

#### N10 · P2 · Claiming a task re-sorts every pending task; this needs measuring under load

`_claim_next_task` (`runs/queue.py:268-327`) filters on a join to `runs`, a `NOT IN (live workers)` subquery and a JSON `LIKE` on `agent_states`. It then sorts on `_stage_priority()` and `_running_in_run()`, and both of those contain a correlated `count(*)` over the same run's tasks. The planner has to evaluate those subqueries for every pending row before `LIMIT 1`.

Every claim loop in every worker runs this on every wake. One wide run can create hundreds of pending tasks, one per professor, so claim cost grows with backlog size multiplied by loop count. The only supporting index is the plain index on `status`.

**Measure first:** seed about 5,000 pending tasks across about 20 runs, then run `EXPLAIN (ANALYZE, BUFFERS)` on the claim query. If it scans the pending set, add these:

- a partial index `ON research_tasks (run_id, created_at) WHERE status = 'pending'`;
- a stored stage-priority column;
- running counts per run taken from a CTE computed once, not per row.

### API shape

#### N11 · P2 · Collection endpoints are unpaginated

`GET /runs` (`runs/routes_runs.py:125`, which loads whole `Run` rows plus per-run progress), `/schools`, `/programs` and `/cv/documents` return every row the account owns. Candidates and tasks are already paged. For a long-lived account, the dashboard's list request grows with its history, which is what F13 describes for conversations.

**Fix:** cursor pagination on created-at and id for each list endpoint, with infinite scroll in the UI using the existing `useInfiniteQuery` pattern. Project only the columns each list renders.

### Storage and deployment architecture

#### N12 · P2 · Files are on a local volume that the API and worker share

CV files, versions, previews and export archives sit on a named Docker volume mounted into both `api` and `worker` (`docker-compose.yml:63-66`, `:95-98`). Both must therefore run on the same host. Backups need a filesystem snapshot alongside `pg_dump`, and the two can drift (F11). This is the main thing stopping the worker from moving to its own machine or being autoscaled.

**Fix:** put an object-storage interface (S3-compatible) behind the existing storage helpers, with the local filesystem as the development backend. Store object keys in the database instead of paths.

#### N13 · P2 · No real observability

There are 37 `print(...)` calls on runtime paths (the worker's whole progress log included) against 25 module loggers, and logging is never configured anywhere. There are no request IDs, no metrics and no error tracker. The production checklist already marks Sentry "not wired yet."

None of these signals exists today:

- queue depth;
- claim latency;
- pool checkouts in use;
- open SSE streams;
- model call latency and error rate per provider.

You would not know that N1, N2 or N10 was happening until users reported it.

**Fix:**

- Configure `logging` once, as JSON, and replace runtime `print` calls.
- Add a request-ID middleware and log the ID with task and run IDs.
- Expose `/metrics` with the gauges above.
- Wire Sentry, or a similar error tracker, into both processes.

### Frontend

#### N14 · P3 · Every open tab polls three status endpoints

`useReady`, `useHealth` and `useWorkers` each refetch every 15 s (`webapp/src/lib/queries.ts:15,31,41`), which is 12 requests per minute per visible tab before any page data. React Query pauses this in hidden tabs, so the cost is per active user. It is small, but it adds up at scale, and `/health` authenticates on every call.

**Fix:** combine the three into one status endpoint, or carry worker and readiness status on a stream the app already has open.

#### N15 · P3 · Frontend test coverage is thin, and CI doesn't run it

The webapp has 22 test files for about 37,000 lines. The largest components, `GradisChat` (1,269 lines), `DocumentWorkspace` (1,267) and `GradisProvider` (1,084), have little or no direct coverage. Together with F14, a broken UI reaches `main` as long as it type-checks.

**Fix:** run Vitest in CI first (F14). Then add tests on the streaming state machines (`GradisProvider`, `useRunEvents`, `useLiveDraft`) before anything else.

---

## 3. Suggested order

**Before a public launch (P0/P1):**

1. F01, F04, F06: production config must fail closed. Don't publish Postgres, require the secrets, require real mail.
2. F05: a hard spend ceiling that applies regardless of plan.
3. N1: Gradis must not hold connections or transactions across model calls. This is cheap to fix and the most likely first outage.
4. N6: proxy headers, so per-IP limits and logs are correct.
5. N2: one `LISTEN` per process, and a 503 instead of hanging.
6. N4: an append-only trace, before traces get long in production.
7. F02, F03, F07, F08: the remaining security items.
8. N5: either move shared state to the database or enforce one API process. Choose one deliberately.

**Before scaling out (P2):** N3, N7, N8, N9, N10 (measure first), N11, N12, N13, F09, F10, F11, F13, F14.

**Polish:** N14, N15, F12.

### What is already in good shape

These were checked during this review and need no work:

- **Task claims:** `SKIP LOCKED`, leases with fencing, and heartbeat-based reaping. Concurrent workers do not double-process.
- **Spend reservations:** stored in Postgres under per-account advisory locks, so concurrent calls cannot overshoot a ceiling.
- **Worker database use:** the orchestrator commits before every model call, so worker loops hold no connection while they wait.
- **Shared HTTP clients:** search, fetch and OpenAlex reuse one client per process, with concurrency ceilings.
- **Run feed queries:** the feed selects only the columns it needs, collects frames before yielding, and has a sweep that catches missed notifications.
- **Raw HTML in the frontend:** the one `innerHTML` sink (`documents/editor/tables.ts:262`) escapes its input before adding markup.
