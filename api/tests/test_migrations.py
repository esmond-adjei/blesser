"""Scratch databases on the suite's Postgres server (override with TEST_DATABASE_URL)."""

import asyncio
import contextlib
import json
import os
import uuid
from urllib.parse import urlsplit, urlunsplit

import asyncpg
from alembic.config import Config

from alembic import command

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://blesser:blesser@localhost:5432/blesser_test",
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
    name = f"blesser_mig_{uuid.uuid4().hex[:8]}"
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
        _fetch(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    )
    return sorted(r["tablename"] for r in rows)


EXPECTED_TABLES = sorted(
    [
        "applicant_profiles",
        "applicant_projects",
        "applicant_documents",
        "applicant_document_projects",
        "applicant_answers",
        "auth_extension_sessions",
        "autofill_daily_usage",
        "autofill_corrections",
        "autofill_reports",
        "sources",
        "crawl_candidates",
        "page_cache",
        "crawl_hosts",
        "audit_log",
        "assistant_conversations",
        "assistant_messages",
        "scan_finds",
        "organization_aliases",
        "duplicate_dismissals",
        "collections",
        "collection_items",
        "opportunity_reports",
        "opportunity_slug_history",
        "site_content",
        "site_settings",
        "alembic_version",
        "applications",
        "auth_email_tokens",
        "auth_refresh_tokens",
        "calendar_feeds",
        "notification_preferences",
        "notifications",
        "opportunities",
        "push_subscriptions",
        "scan_tasks",
        "scans",
        "todos",
        "user_identities",
        "users",
        "worker_heartbeats",
    ]
)


def test_fresh_upgrade_builds_full_schema():
    with _scratch_db() as url:
        command.upgrade(_cfg(url), "head")
        assert _tables(url) == EXPECTED_TABLES


def test_models_and_migrations_agree():
    """A model change without a migration fails here (same check as `alembic check`)."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy.ext.asyncio import create_async_engine

    import api.models  # noqa: F401
    from api.core.db import Base

    async def diff(url: str):
        engine = create_async_engine(url)
        try:
            async with engine.connect() as conn:
                return await conn.run_sync(
                    lambda sync: compare_metadata(
                        MigrationContext.configure(sync), Base.metadata
                    )
                )
        finally:
            await engine.dispose()

    with _scratch_db() as url:
        command.upgrade(_cfg(url), "head")
        assert _run(diff(url)) == []


def test_downgrade_upgrade_cycle():
    with _scratch_db() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        assert _tables(url) == ["alembic_version"]
        command.upgrade(cfg, "head")
        assert _tables(url) == EXPECTED_TABLES


def test_autofill_migration_backfills_normalized_answers_and_preserves_content():
    with _scratch_db() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "0004_applicant_kit")
        _run(
            _fetch(
                url,
                "INSERT INTO users (id, email, password_hash, role) VALUES ('member', 'migration@example.com', '!oauth', 'member')",
            )
        )
        _run(
            _fetch(
                url,
                "INSERT INTO applicant_answers (id, user_id, question, answer, tags, word_count) VALUES ('answer', 'member', 'Describe your résumé (maximum 50 words)?', 'Original answer.', '[]', 2)",
            )
        )
        command.upgrade(cfg, "head")

        row = _run(
            _fetch(
                url,
                "SELECT question, normalized_question, answer FROM applicant_answers WHERE id = 'answer'",
            )
        )[0]
        assert dict(row) == {
            "question": "Describe your résumé (maximum 50 words)?",
            "normalized_question": "describe your resume",
            "answer": "Original answer.",
        }
        assert (
            _run(
                _fetch(
                    url,
                    "SELECT similarity(normalized_question, 'describe your resume') AS score FROM applicant_answers",
                )
            )[0]["score"]
            == 1.0
        )
        command.downgrade(cfg, "0004_applicant_kit")
        assert (
            _run(
                _fetch(url, "SELECT answer FROM applicant_answers WHERE id = 'answer'")
            )[0]["answer"]
            == "Original answer."
        )
        command.upgrade(cfg, "head")


def test_autofill_v2_backfills_birth_fields_and_preserves_explicit_values():
    with _scratch_db() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "0005_autofill")
        _run(
            _fetch(
                url,
                "INSERT INTO users (id, email, password_hash, role) VALUES ('old', 'old@example.com', '!oauth', 'member'), ('explicit', 'explicit@example.com', '!oauth', 'member')",
            )
        )
        _run(
            _fetch(
                url,
                """
            INSERT INTO applicant_profiles (user_id, data, sensitive)
            VALUES ('old', '{"given_name":"Ama"}', 'encrypted-placeholder'),
                   ('explicit', '{"country_of_birth":"Ghana","place_of_birth":"Kumasi"}', 'encrypted-placeholder')
        """,
            )
        )
        command.upgrade(cfg, "head")
        rows = _run(
            _fetch(url, "SELECT user_id, data FROM applicant_profiles ORDER BY user_id")
        )
        assert {row["user_id"]: json.loads(row["data"]) for row in rows} == {
            "old": {"given_name": "Ama", "country_of_birth": "", "place_of_birth": ""},
            "explicit": {"country_of_birth": "Ghana", "place_of_birth": "Kumasi"},
        }
        command.downgrade(cfg, "0005_autofill")
        data = _run(
            _fetch(url, "SELECT data FROM applicant_profiles WHERE user_id = 'old'")
        )[0]["data"]
        assert json.loads(data) == {"given_name": "Ama"}
        command.upgrade(cfg, "head")


def test_editorial_migration_preserves_data_and_reverses_states():
    with _scratch_db() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "0001")
        _run(
            _fetch(
                url,
                """
            INSERT INTO opportunities
              (id, title, organization, category, kind, summary, eligibility, benefits,
               location, countries, requirements, tags, deadline, rolling, link,
               source_url, status, source, dedupe_key)
            SELECT id, 'Same Grant', '', 'startup', 'grant', '', '', '', '', '[]',
                   '[]', '[]', '', false, '', '', status, source, id
            FROM (VALUES ('one', 'pending', 'community'), ('two', 'pending', 'agent'),
                         ('three', 'published', 'agent'), ('four', 'hidden', 'agent'))
                 AS seed(id, status, source)
        """,
            )
        )
        command.upgrade(cfg, "head")
        rows = _run(
            _fetch(
                url,
                "SELECT id, status, audience, review_reason, slug, published_at FROM opportunities",
            )
        )
        by_id = {r["id"]: r for r in rows}
        assert by_id["one"]["status"] == by_id["two"]["status"] == "in_review"
        assert by_id["one"]["review_reason"] == "new_submission"
        assert by_id["two"]["review_reason"] == "agent_find"
        assert by_id["three"]["status"] == "published"
        assert by_id["three"]["audience"] == "public"
        assert by_id["three"]["published_at"] is not None
        assert by_id["four"]["status"] == "hidden"
        assert len({r["slug"] for r in rows}) == 4
        assert all(r["slug"].startswith("same-grant") for r in rows)
        _run(
            _fetch(
                url, "UPDATE opportunities SET status = 'archived' WHERE id = 'three'"
            )
        )
        _run(_fetch(url, "UPDATE opportunities SET status = 'draft' WHERE id = 'four'"))
        command.downgrade(cfg, "0001")
        rows = _run(_fetch(url, "SELECT id, status FROM opportunities"))
        assert {r["id"]: r["status"] for r in rows} == {
            "one": "pending",
            "two": "pending",
            "three": "hidden",
            "four": "pending",
        }
        command.upgrade(cfg, "head")
        assert len(_run(_fetch(url, "SELECT slug FROM opportunities"))) == 4


def test_listing_freshness_rekeys_cycles_and_parks_collisions():
    with _scratch_db() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "0010_ghana_sources")
        _run(
            _fetch(
                url,
                """
                INSERT INTO opportunities (id, slug, audience, editor_note, title, organization,
                    category, kind, summary, eligibility, benefits, location, countries,
                    requirements, tags, deadline, rolling, link, source_url, status, source,
                    dedupe_key, verified_at, created_at, updated_at)
                SELECT v.id, v.id, 'public', '', v.title, v.org, 'student', 'scholarship', '',
                    '', '', '', '[]', '[]', '[]', '', false, '', '', v.status, 'agent', v.key,
                    v.verified, now(), now()
                FROM (VALUES
                    ('a', 'Scholars Program 2026', 'Mastercard Foundation', 'archived',
                     'mastercard foundation|scholars program 2026', NULL::timestamp),
                    ('b', 'Scholars Program 2027', 'Mastercard Foundation', 'published',
                     'mastercard foundation|scholars program 2027', now()),
                    ('c', 'In-Country Scholarships', 'German Academic Exchange Service',
                     'published', 'german academic exchange service|in country scholarships',
                     NULL::timestamp)
                ) AS v(id, title, org, status, key, verified)
                """,
            )
        )
        command.upgrade(cfg, "head")
        rows = _run(_fetch(url, "SELECT id, dedupe_key FROM opportunities ORDER BY id"))
        assert {r["id"]: r["dedupe_key"] for r in rows} == {
            "a": "mastercard|scholars program#a",
            "b": "mastercard|scholars program",
            "c": "daad|in country scholarships",
        }
        aliases = _run(_fetch(url, "SELECT count(*) AS n FROM organization_aliases"))
        assert aliases[0]["n"] > 0
        command.downgrade(cfg, "0010_ghana_sources")
        command.upgrade(cfg, "head")
