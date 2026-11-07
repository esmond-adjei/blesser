import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5-5"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Agent model ---
    # anthropic | openai | ollama | gemini | openai-compatible.
    llm_provider: str = "anthropic"
    llm_model: str = DEFAULT_ANTHROPIC_MODEL
    llm_api_key: str = ""
    llm_base_url: str | None = None
    llm_max_tokens: int = 4096
    # Anthropic prompt caching on tools, system prompt and history.
    llm_prompt_cache: bool = True
    # Hosts (host or host:port, comma-separated) LLM_BASE_URL may target over plain
    # http or a private address (e.g. a self-hosted Ollama).
    allowed_provider_hosts: str = ""
    # Per-request model timeout (seconds); keep well under the stale-task window.
    llm_timeout_seconds: float = 120.0
    # Whole-call deadline for one agent turn, retries included (0 = none).
    llm_call_deadline_seconds: float = 150.0
    # Concurrent model calls per worker process to one backend (0 = no cap).
    llm_max_concurrency: int = 0
    ollama_max_concurrency: int = 2
    # Extra retries with backoff for a transient model failure (timeout, 429/5xx).
    llm_turn_retries: int = 2
    llm_retry_backoff_seconds: float = 10.0
    # A task still failing transiently is requeued until claimed this many times.
    max_task_attempts: int = 3

    # --- Agent budgets ---
    max_agent_turns: int = 40
    # Finishing without saving anything is nudged back to work this many times.
    max_empty_finish_nudges: int = 2
    # Tool results older than this many turns become a marker; <=0 disables.
    max_tool_result_age_turns: int = 2
    # Compaction moves in blocks of this many turns so prompt caches keep hitting.
    compaction_block_turns: int = 3
    # Read-only tools in one turn run concurrently up to this.
    agent_parallel_tool_calls: int = 6

    # --- Opportunities ---
    # What one discover_opportunities task, and one scan, may save.
    max_opportunities_per_task: int = 15
    max_opportunities_per_run: int = 40
    # Region a scan targets when none is given.
    opportunity_default_region: str = "Ghana"
    # Agent saves are grounded in a page the agent read, so they publish straight
    # away; false holds them for an ops admin (OPS_ADMIN_EMAILS) to publish.
    opportunity_auto_publish: bool = True
    # Scheduled refresh: every N hours the worker scans every category as this
    # existing account. Empty email or 0 turns it off.
    opportunity_sweep_email: str = ""
    opportunity_sweep_hours: int = 0
    # Comma-separated emails that may moderate the catalogue (once verified).
    ops_admin_emails: str = ""

    # --- Web search and page fetches (api/web.py) ---
    # Ordered search chain, e.g. "tavily,brave"; empty = [SEARCH_PROVIDER].
    # Keyless duckduckgo is opt-in only.
    search_providers: str = ""
    search_provider: str = "tavily"
    # Key for SEARCH_PROVIDER; TAVILY_API_KEY / BRAVE_API_KEY name a provider's own.
    search_api_key: str = ""
    tavily_api_key: str = ""
    brave_api_key: str = ""
    # Serve recent results for an identical query when every provider fails.
    search_cache_seconds: int = 6 * 3600
    # Reuse an identical query's results this recent (0 = always search).
    search_reuse_seconds: int = 3600
    search_results_for_model: int = 5
    search_snippet_chars: int = 200
    fetch_cache_seconds: int = 6 * 3600
    # Identifies page fetches to site operators; robots.txt is honoured for it.
    fetch_user_agent: str = "BlesserBot/1.0 (opportunity discovery)"
    respect_robots_txt: bool = True
    # After a direct fetch fails: "archive" = Internet Archive. Empty disables.
    fetch_fallbacks: str = "archive"
    # Characters of page text per fetch_page call (the agent pages through the rest).
    fetch_max_chars: int = 4000
    # Raw bytes read per page before extraction.
    fetch_max_bytes: int = 2_000_000
    http_search_concurrency: int = 5
    http_fetch_concurrency: int = 8

    # --- Worker and queue ---
    # Running tasks without a live worker for this long are requeued.
    stale_task_minutes: int = 15
    # Seconds between liveness writes; stale beyond 4x.
    worker_heartbeat_seconds: int = 15
    # Finished tasks' traces are pruned after this many days; <=0 keeps them.
    trace_retention_days: int = 90

    # --- Database and HTTP ---
    database_url: str = "postgresql+asyncpg://blesser:blesser@localhost:5432/blesser"
    # Must exceed worker concurrency plus the housekeeping loops.
    db_pool_size: int = 10
    db_max_overflow: int = 10
    # Comma-separated origins, or "*" for open dev.
    cors_origins: str = "*"
    # Request bodies are capped here before they are read.
    max_request_bytes: int = 1024 * 1024
    # Per-account throttles (core/ratelimit.py).
    rate_limits_enabled: bool = True

    # --- Email (core/mailer.py) ---
    # "console" logs messages (dev/tests); "smtp" relays through any provider.
    mail_backend: str = "console"
    mail_from: str = "Blesser <no-reply@localhost>"
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    # Public URL of the web app, for links in emails and calendars.
    app_base_url: str = "http://localhost:5173"
    # Public origin of the API for calendar feed links; empty = APP_BASE_URL
    # (right when the web app proxies /api).
    public_api_url: str = ""
    password_reset_minutes: int = 30
    email_verify_hours: int = 24
    email_verify_resend_seconds: int = 60

    # --- Notifications ---
    # Browser push is off while either VAPID key is unset (scripts/vapid_keys.py).
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = ""
    # Push + email sends per account per hour; past it, inbox only.
    notification_hourly_cap: int = 20
    # Backstop for the worker's delivery loop (it also wakes on a notify).
    notification_deliver_seconds: float = 30.0

    # --- Auth ---
    # Production must set AUTH_SECRET, or every restart signs everyone out.
    auth_secret: str = ""
    # Fernet key for stored secrets; derived from AUTH_SECRET when unset.
    secrets_key: str = ""
    auth_access_minutes: int = 15
    auth_refresh_days: int = 7
    auth_login_attempts: int = 5
    auth_login_window_seconds: int = 60
    # Bump when the Terms or Privacy notice change; stored per account at sign-up.
    terms_version: str = "2026-11-07"
    # Google sign-in shows when both are set. Redirect URI: {APP_BASE_URL}/auth/callback/google
    oauth_google_client_id: str = ""
    oauth_google_client_secret: str = ""

    def resolve_llm_api_key(self) -> str:
        if self.llm_api_key:
            return self.llm_api_key
        if self.llm_provider.lower() in ("ollama", "openai-compatible"):
            return "ollama"  # local servers accept any key
        return ""

    def resolve_llm_base_url(self) -> str | None:
        provider = self.llm_provider.lower()
        if provider == "ollama":
            return self.llm_base_url or "http://localhost:11434/v1"
        if provider == "gemini":
            return self.llm_base_url or "https://generativelanguage.googleapis.com/v1beta/openai/"
        return self.llm_base_url

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
    if not s.resolve_llm_api_key():
        warnings.append("LLM_API_KEY is not set: scans cannot run.")
    if not (s.search_api_key or s.tavily_api_key or s.brave_api_key or "duckduckgo" in s.search_providers):
        warnings.append("No web search key (TAVILY_API_KEY or BRAVE_API_KEY): scans cannot search.")
    return warnings


def log_config_warnings() -> None:
    for warning in config_warnings():
        log.warning(warning)
