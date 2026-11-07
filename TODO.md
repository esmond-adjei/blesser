# TODO

The current list of production work is [docs/production-readiness-review.md](docs/production-readiness-review.md) (findings F01–F14 and N1–N15, with a suggested order). This file keeps the open items from the 2026-10-15 audit that the review doesn't cover. That audit's full write-up is in git history (`docs/audit/01-findings.md`, last at `921cb31e`).

Rechecked against the code on 2026-10-31. Every P0/P1 item from that audit (#71–#88) is closed, as are C2–C7, E1, X2, X3, X7 and AR1, AR2, AR5.

## P2

- [ ] **S4** Auth abuse controls: `/auth/register` has no per-IP limit, `/auth/verify/send` has a 60 s cooldown but no daily cap, the login throttle is keyed on email only (anyone can lock an account out), and unknown emails skip bcrypt. Proxy IPs: see N6; in-memory buckets: see N5. — `api/api/auth/security.py`, `auth/email_flows.py`
- [ ] **S5** Production config fails open: no production mode that refuses console mail, a missing `AUTH_SECRET` or `CORS_ORIGINS=*` (F04, F06), and no CSP, HSTS, `nosniff` or frame-ancestors headers in `webapp/nginx.conf`.
- [ ] **S6** Refresh tokens: no reuse detection or token family, no row lock on refresh, no "sign out everywhere", and the refresh token sits in `localStorage` (`webapp/src/lib/auth.tsx`). Password change: see F07.
- [ ] **A3** A confirmation pause answers only the first gated tool call; other calls in the same model response are left without a result, which Anthropic rejects on resume. — `api/api/assistant/service.py` (`confirm_required` branch)
- [ ] **A4** The approval card shows a draft's subject only; the body is in a collapsed raw-JSON block. — `webapp/src/components/gradis/GradisChat.tsx`, `assistant/tools.py:describe_call`
- [ ] **G3** `save_program` doesn't check that `department_url` was fetched or came from search results. — `api/api/prospects/tools.py`
- [ ] **G4** No offline eval harness (scoring precision, citation-gate cases, draft rubric) and no prompt version stored on tasks.
- [ ] **Q3** No SIGTERM handling in the worker: a deploy strands in-flight tasks until the reaper requeues them. (Attempt limits and transient retries are done.) — `api/api/worker.py`, `runs/queue.py`
- [ ] **Q4** Claim order is fair between runs (fewest running first) but not between accounts. — `api/api/runs/queue.py:_claim_next_task`
- [ ] **Q5** OpenAI-compatible provider: string-encoded tool arguments (Ollama) aren't re-parsed, and missing or duplicate tool-call ids aren't synthesised. — `api/api/agent/llm/openai_compat_provider.py`
- [ ] **Q6** Gradis `score_alignment` calls the synchronous `embed_and_score` on the event loop, and bcrypt runs directly in async handlers. — `api/api/assistant/tools.py`, `auth/service.py`
- [ ] **Q7** Tests share a fixed `graduator_test` database, so concurrent runs collide; `test_account_isolation.py` probes routes without the `/api` prefix.
- [ ] **X4** The live stream falls back to polling for good when a *reconnect* receives no frames; only the first connect should count. — `webapp/src/lib/queries.ts`
- [ ] **X5** Accessibility: `components/ui/dialog.tsx` has no focus trap, initial focus or restore; icon-only links in the mobile bar have no labels.
- [ ] **X6** Phone top bar: five icon links plus the wordmark overflow at 360–390 px and duplicate the drawer. — `webapp/src/components/layout/AppShell.tsx` (`MobileBar`)
- [ ] **O3** `listener_dsn()` drops `DATABASE_URL` query parameters (e.g. `sslmode`) for LISTEN connections. — `api/api/core/db.py`
- [ ] **R1** Gradis re-declares the pipeline tool schemas instead of building them from `TOOL_DEFINITIONS`. — `api/api/assistant/tools.py`
- [ ] **R2** Gradis writes email drafts directly, without the outreach drafting prompt. — `api/api/assistant/tools.py:_save_email_draft`

## P3

- [ ] **S8** `/health` returns the operator's LLM and embedding base URLs, and `runs/health.py` returns raw database exception text.
- [ ] **S9** The OAuth PKCE verifier travels in the signed but readable `state`; `/auth/oauth/link` has no password-attempt throttle. — `api/api/auth/oauth.py`
- [ ] **Q8** Run completion doesn't lock the run row, so a run can be marked done while a task is pending. — `api/api/runs/lifecycle.py`
- [ ] **X8** Row menus appear only on hover, so touch users can't see them. — `webapp/src/components/ui/row-menu.tsx`
- [ ] **R3** Unused code: `HealthPill`, `listAssistantTools` and the `GET /assistant/tools` route.
- [ ] **R4** Hand-written TS types mirror the Pydantic schemas; generate them with `openapi-typescript` and diff in CI.

## Architecture

- [ ] **AR3** Shared knowledge base for public data. Tracked in #198 (deferred) and #233.
