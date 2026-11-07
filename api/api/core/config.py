import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Bring-your-own-model: agent LLM ---
    # Agent LLM provider: anthropic | openai | ollama | gemini | openai-compatible.
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-6"
    # Smaller model for short single-purpose calls (code-first save, email drafts).
    # Empty = llm_model. Only system-model (Auto) runs use it.
    llm_small_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str | None = None
    llm_max_tokens: int = 4096
    # System model's context window in tokens for the chat usage bar; None hides it.
    llm_context_window: int | None = None
    # Anthropic prompt caching: breakpoints on tools/system prompt and the end of
    # history. OpenAI and Gemini cache on their own.
    llm_prompt_cache: bool = True
    # Hosts (host or host:port, comma-separated) a user's provider base URL may
    # target over plain http or a private address (e.g. self-hosted Ollama).
    allowed_provider_hosts: str = ""
    # Per-request model timeout (seconds; SDKs retry twice). Keep well under the
    # stale-task window.
    llm_timeout_seconds: float = 120.0
    # Resolve each school to its OpenAlex institution so affiliations match by id.
    openalex_resolve_institutions: bool = True
    # Rank a programme's faculty by recent works on the topic before researching.
    openalex_rank_faculty: bool = True
    # Narrow tasks score in code first; the model only writes a match's rationale.
    deterministic_research: bool = True
    # Whole-call deadline for an agent model turn, retries included (0 = none).
    llm_call_deadline_seconds: float = 150.0
    # Concurrent model calls per worker process to one backend (0 = no cap); the
    # deadline starts once a slot is held. Ollama queues past a few requests, so
    # match OLLAMA_MAX_CONCURRENCY to the server's OLLAMA_NUM_PARALLEL.
    llm_max_concurrency: int = 0
    ollama_max_concurrency: int = 2
    # Extra retries with backoff for a transient model failure (timeout, 429/5xx).
    llm_turn_retries: int = 2
    llm_retry_backoff_seconds: float = 10.0
    # A task still failing transiently is requeued until claimed this many times.
    max_task_attempts: int = 3

    # --- Bring-your-own-model: embeddings ---
    # Embedding provider: voyage | openai | ollama | gemini | openai-compatible | local.
    embedding_provider: str = "voyage"
    embedding_model: str = ""
    embedding_api_key: str = ""
    embedding_base_url: str | None = None

    search_api_key: str = ""
    search_provider: str = "tavily"
    # Ordered search chain; empty = [SEARCH_PROVIDER]. Keyless duckduckgo (an HTML
    # scrape its terms likely forbid) is opt-in only. Legacy SEARCH_API_KEY serves
    # SEARCH_PROVIDER.
    search_providers: str = ""
    tavily_api_key: str = ""
    brave_api_key: str = ""
    # Serve recent results for an identical query when every provider fails.
    search_cache_seconds: int = 6 * 3600
    # Reuse an identical query's results this recent (0 = always search).
    search_reuse_seconds: int = 3600
    # Results and snippet size shown to the model; full pages are a fetch_page away.
    search_results_for_model: int = 5
    search_snippet_chars: int = 200
    # Abstract length shown by get_author_works unless full=true; scoring reads all.
    works_abstract_chars: int = 300
    # Extracted pages kept for reuse across tasks and runs.
    fetch_cache_seconds: int = 6 * 3600
    # OpenAlex responses (author searches, works lists) kept for reuse.
    openalex_cache_seconds: int = 24 * 3600
    # Postgres cache shared across processes and restarts: most responses this
    # many days, author lists and institution lookups the longer one. 0 = off.
    openalex_db_cache_days: int = 7
    openalex_db_cache_long_days: int = 30
    # Pages of 200 authors to scan in the school's author list (a tenth of a
    # search's price) before searching by name. 0 = always search.
    openalex_roster_pages: int = 5
    # Roster-first faculty lists: one model call reads the department page's names;
    # at least this many names skips the supervisor's agent loop. Kept this many
    # days. 0 days = no store; 0 names = off.
    roster_min_names: int = 3
    faculty_roster_days: int = 30
    # Per-account professor index: reuse an entry at most this many days old
    # instead of looking the professor up again. 0 = off.
    professor_index_days: int = 30
    # Characters of a listing page shown to the extraction call.
    roster_page_chars: int = 15000
    # Last resort with no readable faculty page: OpenAlex authors at the school
    # with at least this many on-topic works there.
    roster_seed_min_works: int = 2
    # Supervisor agent-loop turns when the roster-first path falls back to it.
    supervisor_max_turns: int = 15
    # Embedding vectors kept per (provider, model, text).
    embedding_cache_seconds: int = 7 * 24 * 3600
    # Identifies page fetches to site operators (no browser impersonation);
    # robots.txt is honoured for it.
    fetch_user_agent: str = (
        "GraduatorBot/0.4 (research assistant for students)"
    )
    respect_robots_txt: bool = True
    # OpenAlex "polite pool" contact (mailto: in the User-Agent). Without it, more
    # 429s; startup warns.
    openalex_mailto: str = ""
    # OpenAlex API key (Bearer). Without one, the server IP shares a free budget of
    # about $0.10/day (~100 author searches); a free key gets ~$1/day.
    openalex_api_key: str = ""
    # After OpenAlex's daily budget resets, waiting tasks resume spread over this.
    openalex_resume_spread_seconds: int = 600
    # Retry interval for a rejected OpenAlex key (401/403), so a fix needs no restart.
    openalex_auth_recheck_seconds: int = 300
    # Other verification sources (docs/verification-sources.md); remove a name to
    # disable. faculty_page runs before OpenAlex, the rest only when OpenAlex has
    # nobody or is down. dblp: computing only; nih/nsf: US or unknown-country
    # schools. semantic_scholar only adds abstracts by DOI.
    verification_sources: str = "faculty_page,dblp,nih,nsf,orcid,semantic_scholar"
    # Per request to DBLP, ORCID, NIH RePORTER, NSF and Semantic Scholar (seconds).
    source_timeout_seconds: float = 10.0
    # Least gap between two requests to one source, process-wide (seconds); NIH
    # asks for at most 1/s, DBLP throttles bursts.
    source_min_interval_seconds: dict[str, float] = {
        "dblp": 1.0, "nih": 1.0, "nsf": 1.0, "orcid": 0.5, "semantic_scholar": 1.1,
    }
    # Optional: Semantic Scholar's own limit instead of the shared keyless one.
    semantic_scholar_api_key: str = ""
    # A request that would wait longer than this for its slot is skipped.
    source_max_queue_seconds: float = 15.0
    # After a failure (timeout, 5xx, 429) a source is skipped this long.
    source_outage_seconds: int = 300
    # Successful responses kept in process; Postgres keeps them per OPENALEX_DB_CACHE_DAYS.
    source_cache_seconds: int = 24 * 3600
    # Finished tasks' traces are pruned after this many days; <=0 keeps them.
    trace_retention_days: int = 90
    # Tool results past this many characters are stored truncated, a guard against
    # pathological payloads. <=0 stores everything.
    tool_log_max_chars: int = 1_000_000
    # Bump when the Terms or Privacy notice change; stored per account at sign-up.
    terms_version: str = "2026-10-15"
    # Fallbacks after a direct page fetch fails ("archive" = Internet Archive). Empty disables.
    fetch_fallbacks: str = "archive"
    database_url: str = "postgresql+asyncpg://graduator:graduator@localhost:5432/graduator"

    # Comma-separated origins, or "*" for open dev.
    cors_origins: str = "*"

    # --- TypeSafe semantic judgments (opt-in) ---
    # Second-stage rationale verifier for paraphrases the substring check rejects.
    typesafe_api_key: str = ""
    typesafe_rationale_check: bool = False
    # Pick the right OpenAlex author when several at the school share the
    # name, instead of handing the professor to the full agent loop.
    typesafe_author_pick: bool = False
    # Rate how well a professor's papers fit the interests: shown beside the
    # similarity, and a confident fit stops an "unrelated" score concluding no match.
    typesafe_fit_rating: bool = False
    # Pinned: jev-latest moves and would drift the tuned auto_accept threshold.
    typesafe_model: str = "jev-1.13.0"
    typesafe_auto_accept: float = 0.8

    # Safety valve: hard cap on tool-call turns per agent task.
    max_agent_turns: int = 40

    # Progress floor: empty finishes get nudged back to work, bounded by this.
    max_empty_finish_nudges: int = 2

    # Anti-runaway: max new entities one agent task may create.
    max_programs_per_task: int = 12
    # Backstop for direct research flows; fanned-out narrow tasks save one professor each.
    max_professors_per_task: int = 10
    max_drafts_per_task: int = 3

    # --- Scaling + reliability ---
    # Total candidates per run, checked via live COUNT in dispatch().
    max_candidates_per_run: int = 30
    # Fan-out cap: max professor-research tasks one spawn call may queue.
    max_spawn_per_call: int = 20
    # Convergence caps, overridable per run; together they bound total work.
    max_programs_per_run: int = 10
    # Schools a person may add to one run; an anti-runaway bound.
    max_user_programs_per_run: int = 50
    # Hand-added, unresearched professors per run: they bypass the candidate cap.
    max_user_professors_per_run: int = 50
    # Per-account throttles on uploads and AI endpoints (core/ratelimit.py).
    rate_limits_enabled: bool = True

    # --- Transactional email (core/mailer.py, docs/email.md) ---
    # "console" logs messages (dev/tests); "smtp" relays through any provider.
    mail_backend: str = "console"
    mail_from: str = "Graduator <no-reply@localhost>"
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    # Public URL of the webapp, used to build links in emails.
    app_base_url: str = "http://localhost:5173"
    password_reset_minutes: int = 30
    email_verify_hours: int = 24
    # Minimum gap between verification emails for one account.
    email_verify_resend_seconds: int = 60

    # --- Notifications (api/notifications; docs/notifications.md) ---
    # Push is off while either VAPID key is unset (`python scripts/vapid_keys.py`).
    # The subject is a mailto: or https: contact; MAIL_FROM's address otherwise.
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = ""
    # Push + email sends per account per hour; past it, inbox only.
    notification_hourly_cap: int = 20
    # Backstop for the worker's delivery loop (it also wakes on a notify).
    notification_deliver_seconds: float = 30.0

    # --- Third-party sign-in: a provider shows only when both values are set.
    # Redirect URI: {APP_BASE_URL}/auth/callback/google
    oauth_google_client_id: str = ""
    oauth_google_client_secret: str = ""

    # Daily usage rollups older than this are pruned.
    usage_retention_days: int = 400
    # Comma-separated emails allowed to read the ops usage view.
    ops_admin_emails: str = ""

    # Off during beta: everyone gets Beta (= Pro limits).
    billing_enforced: bool = False
    # Development only: accounts may switch their own plan, and it applies even
    # with BILLING_ENFORCED off. Never enable where real users sign up.
    billing_plan_switch: bool = False
    # Checkout payment provider; nothing real is wired in yet, leave empty.
    # "simulated" is a dev-only test checkout and requires BILLING_PLAN_SWITCH=true.
    billing_provider: str = ""
    # Fall back to the operator's LLM_API_KEY for accounts without a key.
    allow_system_model: bool = True
    # Only verified accounts may spend the operator's key.
    system_model_requires_verified_email: bool = True
    # Per-account daily token ceiling while on the operator key (0 = none).
    system_model_daily_tokens: int = 1_000_000
    # Per-account daily calls to operator-paid tools (search, embedding, re-judge; 0 = none).
    system_daily_tool_calls: int = 2000
    max_professors_per_program: int = 5
    # Narrow tasks per run as a multiple of the candidate cap (room for non-matches).
    research_budget_factor: float = 2.5
    # Model turns for a programme's admissions step.
    index_application_max_turns: int = 6
    # Stop a programme's leads after this many consecutive unrelated professors (0 = off).
    programme_miss_streak: int = 3
    # Per-tool call cap in one professor task (JSON); unlisted tools are uncapped.
    narrow_tool_caps: dict[str, int] = {
        "find_openalex_author": 3,
        "get_author_works": 4,
        "fetch_page": 4,
        "search_web": 4,
    }
    # Context compaction: tool results older than this many turns become a marker; <=0 disables.
    max_tool_result_age_turns: int = 2
    # Compaction moves in blocks of this many turns so the history prefix stays
    # byte-identical for prompt caches. 1 = compact every turn.
    compaction_block_turns: int = 3
    # fetch_page payload cap. Faculty listings need names + links, not essays.
    fetch_max_chars: int = 3000
    # Raw bytes read per fetched page before extraction (memory bound).
    fetch_max_bytes: int = 2_000_000
    # Stale-task reaper: running tasks untouched past this are requeued as pending.
    stale_task_minutes: int = 15
    # Worker heartbeat: seconds between liveness writes; stale beyond 4x, pruned after a day.
    worker_heartbeat_seconds: int = 15
    # Postgres pool: must exceed worker concurrency plus the reaper/heartbeat loops.
    db_pool_size: int = 10
    db_max_overflow: int = 10

    # --- Live event feed (SSE) ---
    # SSE sweep backstop for missed wakes; not the liveness path. Each sweep
    # rechecks every connected stream, so keep it slow.
    sse_sweep_seconds: float = 10.0
    # Cap on concurrent streams: each holds a LISTEN connection outside the pool.
    # Budget against Postgres max_connections with the api and worker pools.
    sse_max_streams: int = 32
    # Live trace frames: max tool-call entries carried in one `trace` frame.
    sse_trace_max_events: int = 60

    # --- Agent execution tuning ---
    # Read-only tools in one turn run concurrently up to this; DB writers stay serial.
    agent_parallel_tool_calls: int = 6
    # Politeness ceilings, shared process-wide across worker loops.
    http_search_concurrency: int = 5
    http_fetch_concurrency: int = 8
    openalex_concurrency: int = 4
    # Fallback poll when no enqueue notification arrives.
    worker_idle_poll_seconds: float = 5.0
    # Failed tasks older than this stop raising the health `degraded` banner.
    health_error_window_minutes: int = 60

    # --- CV editor ---
    # Local append-only file layout (cv/{doc}/...).
    cv_storage_dir: str = "cv_storage"
    # "process" = sandboxed child (scrubbed env, rlimits, timeout, no network
    # where supported); "inline" = in the API process (debugging only).
    cv_sandbox: str = "process"
    # Upload cap: hostile files are rejected before parsing.
    cv_max_upload_bytes: int = 10 * 1024 * 1024
    # Every other request body (JSON) is capped here before it is read.
    max_request_bytes: int = 2 * 1024 * 1024

    # --- Auth (email + password, JWT access + rotating refresh) ---
    # Empty in dev means an ephemeral secret; production must set AUTH_SECRET or
    # every restart invalidates all sessions.
    auth_secret: str = ""
    # Fernet key for stored secrets; derived from AUTH_SECRET when unset.
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    secrets_key: str = ""
    auth_access_minutes: int = 15
    auth_refresh_days: int = 7
    # Login throttle: max failed attempts per email before a lockout window.
    auth_login_attempts: int = 5
    auth_login_window_seconds: int = 60

    def resolve_llm_api_key(self) -> str:
        if self.llm_api_key:
            return self.llm_api_key
        if self.llm_provider.lower() in ("ollama", "openai-compatible"):
            # Local servers accept any key.
            return "ollama"
        return ""

    def resolve_llm_base_url(self) -> str | None:
        provider = self.llm_provider.lower()
        if provider == "ollama":
            return self.llm_base_url or "http://localhost:11434/v1"
        if provider == "gemini":
            return (
                self.llm_base_url
                or "https://generativelanguage.googleapis.com/v1beta/openai/"
            )
        return self.llm_base_url

    def resolve_embedding_api_key(self) -> str:
        return self.embedding_api_key

    def resolve_cors_origins(self) -> list[str]:
        raw = self.cors_origins.strip()
        if raw in ("", "*"):
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


settings = Settings()


def config_warnings(s: Settings | None = None) -> list[str]:
    """Settings a deployment is expected to set but left empty."""
    s = s or settings
    warnings = []
    if not s.openalex_mailto.strip():
        warnings.append(
            "OPENALEX_MAILTO is not set: OpenAlex requests go to the common pool "
            "instead of the polite pool and are rate-limited (429) more often. "
            "Set it to a contact address."
        )
    return warnings


def log_config_warnings() -> None:
    """Log config_warnings() once at API or worker startup."""
    for warning in config_warnings():
        log.warning(warning)
