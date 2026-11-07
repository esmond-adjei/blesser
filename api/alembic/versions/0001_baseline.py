"""Baseline schema: accounts, notifications, opportunities, applications, to-dos and scans.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(), nullable=True),
        sa.Column("terms_accepted_at", sa.DateTime(), nullable=True),
        sa.Column("terms_version", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(), nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("worker_id"),
    )
    op.create_index(
        op.f("ix_worker_heartbeats_last_seen_at"),
        "worker_heartbeats",
        ["last_seen_at"],
        unique=False,
    )
    op.create_table(
        "auth_email_tokens",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_auth_email_tokens_user_id"),
        "auth_email_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "auth_refresh_tokens",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_auth_refresh_tokens_token_hash"),
        "auth_refresh_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_auth_refresh_tokens_user_id"),
        "auth_refresh_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "calendar_feeds",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_table(
        "notification_preferences",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("channels", sa.JSON(), nullable=False),
        sa.Column("quiet_start", sa.String(length=5), nullable=True),
        sa.Column("quiet_end", sa.String(length=5), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("email_digest", sa.Boolean(), nullable=False),
        sa.Column("last_digest_on", sa.Date(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.String(length=500), nullable=False),
        sa.Column("link", sa.String(length=500), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=200), nullable=False),
        sa.Column(
            "in_inbox", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("delivery", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "dedupe_key", name="uq_notifications_user_dedupe"
        ),
    )
    op.create_index(
        "ix_notifications_undelivered",
        "notifications",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("delivered_at IS NULL"),
    )
    op.create_index(
        op.f("ix_notifications_user_id"), "notifications", ["user_id"], unique=False
    )
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(length=255), nullable=False),
        sa.Column("auth", sa.String(length=255), nullable=False),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("last_ok_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint"),
    )
    op.create_index(
        op.f("ix_push_subscriptions_user_id"),
        "push_subscriptions",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "scans",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("region", sa.String(), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("focus", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scans_status"), "scans", ["status"], unique=False)
    op.create_index(op.f("ix_scans_user_id"), "scans", ["user_id"], unique=False)
    op.create_table(
        "user_identities",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "subject", name="uq_user_identities_provider_subject"
        ),
    )
    op.create_index(
        op.f("ix_user_identities_user_id"), "user_identities", ["user_id"], unique=False
    )
    op.create_table(
        "opportunities",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("organization", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("eligibility", sa.Text(), nullable=False),
        sa.Column("benefits", sa.String(), nullable=False),
        sa.Column("location", sa.String(), nullable=False),
        sa.Column("countries", sa.JSON(), nullable=False),
        sa.Column("requirements", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("deadline", sa.String(), nullable=False),
        sa.Column("deadline_date", sa.Date(), nullable=True),
        sa.Column("rolling", sa.Boolean(), nullable=False),
        sa.Column("link", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("dedupe_key", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("scan_id", sa.String(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index(
        op.f("ix_opportunities_category"), "opportunities", ["category"], unique=False
    )
    op.create_index(
        op.f("ix_opportunities_created_by"),
        "opportunities",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_opportunities_deadline_date"),
        "opportunities",
        ["deadline_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_opportunities_kind"), "opportunities", ["kind"], unique=False
    )
    op.create_index(
        op.f("ix_opportunities_scan_id"), "opportunities", ["scan_id"], unique=False
    )
    op.create_index(
        op.f("ix_opportunities_status"), "opportunities", ["status"], unique=False
    )
    op.create_table(
        "scan_tasks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("scan_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("target", sa.String(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "done",
                "error",
                "cancelled",
                name="taskstatus",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("claimed_by", sa.String(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("log", sa.Text(), nullable=True),
        sa.Column("final_text", sa.Text(), nullable=True),
        sa.Column("turns", sa.Integer(), nullable=True),
        sa.Column("messages_json", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_scan_tasks_scan_id"), "scan_tasks", ["scan_id"], unique=False
    )
    op.create_index(
        op.f("ix_scan_tasks_status"), "scan_tasks", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_scan_tasks_user_id"), "scan_tasks", ["user_id"], unique=False
    )
    op.create_table(
        "applications",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("organization", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("location", sa.String(), nullable=False),
        sa.Column("link", sa.String(), nullable=False),
        sa.Column("benefits", sa.String(), nullable=False),
        sa.Column("requirements", sa.JSON(), nullable=False),
        sa.Column("deadline", sa.String(), nullable=False),
        sa.Column("deadline_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("opportunity_id", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"], ["opportunities.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_applications_deadline_date"),
        "applications",
        ["deadline_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_applications_opportunity_id"),
        "applications",
        ["opportunity_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_applications_user_id"), "applications", ["user_id"], unique=False
    )
    op.create_table(
        "todos",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("priority", sa.String(), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=False),
        sa.Column("done_at", sa.DateTime(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.String(), nullable=True),
        sa.Column("application_id", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"], ["opportunities.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_todos_application_id"), "todos", ["application_id"], unique=False
    )
    op.create_index(op.f("ix_todos_done"), "todos", ["done"], unique=False)
    op.create_index(op.f("ix_todos_due_date"), "todos", ["due_date"], unique=False)
    op.create_index(
        op.f("ix_todos_opportunity_id"), "todos", ["opportunity_id"], unique=False
    )
    op.create_index(op.f("ix_todos_user_id"), "todos", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_todos_user_id"), table_name="todos")
    op.drop_index(op.f("ix_todos_opportunity_id"), table_name="todos")
    op.drop_index(op.f("ix_todos_due_date"), table_name="todos")
    op.drop_index(op.f("ix_todos_done"), table_name="todos")
    op.drop_index(op.f("ix_todos_application_id"), table_name="todos")
    op.drop_table("todos")
    op.drop_index(op.f("ix_applications_user_id"), table_name="applications")
    op.drop_index(op.f("ix_applications_opportunity_id"), table_name="applications")
    op.drop_index(op.f("ix_applications_deadline_date"), table_name="applications")
    op.drop_table("applications")
    op.drop_index(op.f("ix_scan_tasks_user_id"), table_name="scan_tasks")
    op.drop_index(op.f("ix_scan_tasks_status"), table_name="scan_tasks")
    op.drop_index(op.f("ix_scan_tasks_scan_id"), table_name="scan_tasks")
    op.drop_table("scan_tasks")
    op.drop_index(op.f("ix_opportunities_status"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_scan_id"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_kind"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_deadline_date"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_created_by"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_category"), table_name="opportunities")
    op.drop_table("opportunities")
    op.drop_index(op.f("ix_user_identities_user_id"), table_name="user_identities")
    op.drop_table("user_identities")
    op.drop_index(op.f("ix_scans_user_id"), table_name="scans")
    op.drop_index(op.f("ix_scans_status"), table_name="scans")
    op.drop_table("scans")
    op.drop_index(
        op.f("ix_push_subscriptions_user_id"), table_name="push_subscriptions"
    )
    op.drop_table("push_subscriptions")
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_index(
        "ix_notifications_undelivered",
        table_name="notifications",
        postgresql_where=sa.text("delivered_at IS NULL"),
    )
    op.drop_table("notifications")
    op.drop_table("notification_preferences")
    op.drop_table("calendar_feeds")
    op.drop_index(
        op.f("ix_auth_refresh_tokens_user_id"), table_name="auth_refresh_tokens"
    )
    op.drop_index(
        op.f("ix_auth_refresh_tokens_token_hash"), table_name="auth_refresh_tokens"
    )
    op.drop_table("auth_refresh_tokens")
    op.drop_index(op.f("ix_auth_email_tokens_user_id"), table_name="auth_email_tokens")
    op.drop_table("auth_email_tokens")
    op.drop_index(
        op.f("ix_worker_heartbeats_last_seen_at"), table_name="worker_heartbeats"
    )
    op.drop_table("worker_heartbeats")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
