"""Scratch databases on the suite's Postgres server (override with TEST_DATABASE_URL)."""

import asyncio
import contextlib
import os
import uuid
from urllib.parse import urlsplit, urlunsplit

import asyncpg
from alembic.config import Config

from alembic import command

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://graduator:graduator@localhost:5432/graduator_test",
)


def _dsn(db_url: str) -> str:
    """Plain asyncpg DSN (SQLAlchemy's +asyncpg driver prefix is its own)."""
    parts = urlsplit(db_url)
    return urlunsplit(("postgresql", parts.netloc, parts.path, "", ""))


def _run(coro):
    return asyncio.run(coro)


async def _admin_execute(sql: str) -> None:
    parts = urlsplit(TEST_DATABASE_URL)
    admin = urlunsplit(("postgresql", parts.netloc, "/postgres", "", ""))
    conn = await asyncpg.connect(admin)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


@contextlib.contextmanager
def _scratch_db():
    name = f"graduator_mig_{uuid.uuid4().hex[:8]}"
    _run(_admin_execute(f'CREATE DATABASE "{name}"'))
    try:
        parts = urlsplit(TEST_DATABASE_URL)
        yield urlunsplit((parts.scheme, parts.netloc, f"/{name}", "", ""))
    finally:
        _run(_admin_execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def _cfg(url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


async def _fetch(url: str, sql: str):
    conn = await asyncpg.connect(_dsn(url))
    try:
        return await conn.fetch(sql)
    finally:
        await conn.close()


def _tables(url: str) -> list[str]:
    rows = _run(
        _fetch(
            url,
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' ORDER BY tablename",
        )
    )
    return sorted(r["tablename"] for r in rows)


def _columns(url: str, table: str) -> list[str]:
    rows = _run(
        _fetch(
            url,
            "SELECT column_name FROM information_schema.columns "
            f"WHERE table_schema = 'public' AND table_name = '{table}' "
            "ORDER BY ordinal_position",
        )
    )
    return [r["column_name"] for r in rows]


def test_faculty_application_tool_migration_preserves_custom_permissions():
    with _scratch_db() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "052_paper_publication_type")

        async def seed():
            conn = await asyncpg.connect(_dsn(url))
            try:
                for user, tools in [
                    ("default", '["search_web", "fetch_page", "spawn_professor_research", "confirm_no_match"]'),
                    ("custom", '["search_web"]'),
                    ("fallback", '[]'),
                ]:
                    await conn.execute("INSERT INTO users (id, email, password_hash) VALUES ($1, $2, 'hash')", user, f"{user}@example.com")
                    await conn.execute("INSERT INTO agent_tasks (user_id, task_type, enabled, tools) VALUES ($1, 'research_professor', true, $2::json)", user, tools)
            finally:
                await conn.close()

        _run(seed())
        command.upgrade(cfg, "head")
        rows = _run(_fetch(url, "SELECT user_id, tools::text AS tools FROM agent_tasks ORDER BY user_id"))
        import json
        values = {row["user_id"]: json.loads(row["tools"]) for row in rows}
        assert values["default"][-1] == "save_application"
        assert values["custom"] == ["search_web"]
        assert values["fallback"] == []


EXPECTED_TABLES = [
    "account_exports",
    "admission_cycles",
    "agent_flows",
    "agent_tasks",
    "agent_tools",
    "alembic_version",
    "applications",
    "assistant_conversations",
    "assistant_messages",
    "assistant_queue",
    "auth_email_tokens",
    "auth_refresh_tokens",
    "candidate_scores",
    "cv_documents",
    "cv_suggestions",
    "cv_tailored_versions",
    "document_folders",
    "email_drafts",
    "faculty_rosters",
    "index_overrides",
    "index_papers",
    "index_professors",
    "match_evidence",
    "match_scores",
    "matches",
    "notification_preferences",
    "notifications",
    "openalex_responses",
    "paper_authors",
    "papers",
    "professor_affiliations",
    "professor_index",
    "professor_optouts",
    "professors",
    "programs",
    "provider_configs",
    "push_subscriptions",
    "research_tasks",
    "run_schools",
    "runs",
    "school_shortlist",
    "schools",
    "tool_call_logs",
    "usage_daily",
    "user_identities",
    "users",
    "worker_heartbeats",
]

EXPECTED_RUN_COLUMNS = [
    "id",
    "region",
    "field",
    "degree_level",
    "interest_statement",
    "status",
    "created_at",
    "interest_embedding",
    "max_programs",
    "max_professors",
    "max_professors_per_program",
    "user_id",
    "flow_id",
    "school_tiers",
    "llm_provider",
    "agent_states",
    "interest_document_id",
]
EXPECTED_TASK_COLUMNS = [
    "id",
    "run_id",
    "task_type",
    "target_id",
    "target_name",
    "status",
    "error",
    "created_at",
    "updated_at",
    "log",
    "final_text",
    "turns",
    "messages_json",
    "input_tokens",
    "output_tokens",
    "started_at",
    "finished_at",
    "user_id",
    "claimed_by",
    "attempt",
    "wait_until",
    "provider",
    "model",
    "cache_read_tokens",
    "model_seconds",
    "tool_seconds",
    "path",
    "path_reason",
]

# research_tasks.status width: fits "cancelled" with headroom.
TASK_STATUS_WIDTH = 16


def _indexes(url: str) -> list[str]:
    rows = _run(
        _fetch(
            url,
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND indexname LIKE 'ix_%'",
        )
    )
    return sorted(r["indexname"] for r in rows)


def test_fresh_upgrade_builds_full_schema():
    with _scratch_db() as url:
        command.upgrade(_cfg(url), "head")
        assert _tables(url) == EXPECTED_TABLES
        assert _columns(url, "runs") == EXPECTED_RUN_COLUMNS
        assert _columns(url, "research_tasks") == EXPECTED_TASK_COLUMNS
        assert _columns(url, "worker_heartbeats") == [
            "worker_id",
            "concurrency",
            "started_at",
            "last_seen_at",
        ]
        indexes = _indexes(url)
        assert "ix_research_tasks_run_id" in indexes
        assert "ix_candidate_scores_run_id" in indexes
        assert "ix_tool_call_logs_task_id" in indexes
        # 008 adds the professor lab affiliation, 009 the bio.
        assert "lab_name" in _columns(url, "professors")
        assert "bio" in _columns(url, "professors")
        assert "bio_source" in _columns(url, "professors")
        # 010 adds the academic social links.
        assert "socials" in _columns(url, "professors")
        # 011 adds the portrait photo URL.
        assert "photo_url" in _columns(url, "professors")
        # 041 adds the schedulable deadline and the notification tables.
        assert "deadline_date" in _columns(url, "applications")
        assert "dedupe_key" in _columns(url, "notifications")
        assert "ix_notifications_undelivered" in indexes
        # 005 widens research_tasks.status past VARCHAR(7).
        status_len = _run(
            _fetch(
                url,
                "SELECT character_maximum_length FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'research_tasks' "
                "AND column_name = 'status'",
            )
        )
        assert status_len[0]["character_maximum_length"] == TASK_STATUS_WIDTH


def test_legacy_upgrade_adds_budget_columns():
    """A pre-Alembic database (no version row) stamps the baseline, then upgrades."""
    with _scratch_db() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "001")
        _run(_fetch(url, "DELETE FROM alembic_version"))
        command.stamp(cfg, "001")
        command.upgrade(cfg, "head")
        assert _columns(url, "runs") == EXPECTED_RUN_COLUMNS
        assert _columns(url, "research_tasks") == EXPECTED_TASK_COLUMNS
        assert "worker_heartbeats" in _tables(url)
        assert "ix_research_tasks_run_id" in _indexes(url)


def test_downgrade_upgrade_cycle():
    with _scratch_db() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        assert _tables(url) == ["alembic_version"]
        command.upgrade(cfg, "head")
        assert _tables(url) == EXPECTED_TABLES
        assert _columns(url, "runs") == EXPECTED_RUN_COLUMNS
        assert _columns(url, "research_tasks") == EXPECTED_TASK_COLUMNS
