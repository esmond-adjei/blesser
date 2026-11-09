"""Separate public, member and staff publishing."""

import sqlalchemy as sa

from alembic import op

revision = "0002_editorial_architecture"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users", sa.Column("role", sa.String(), nullable=False, server_default="member")
    )
    op.add_column("users", sa.Column("disabled_at", sa.DateTime(), nullable=True))
    op.create_check_constraint(
        "ck_user_role", "users", "role IN ('member','editor','admin')"
    )
    op.alter_column("users", "role", server_default=None)
    op.add_column(
        "auth_refresh_tokens",
        sa.Column("audience", sa.String(), nullable=False, server_default="app"),
    )
    op.alter_column("auth_refresh_tokens", "audience", server_default=None)
    op.add_column(
        "opportunities",
        sa.Column("audience", sa.String(), nullable=False, server_default="public"),
    )
    op.add_column("opportunities", sa.Column("slug", sa.String(), nullable=True))
    op.add_column(
        "opportunities", sa.Column("published_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "opportunities",
        sa.Column(
            "published_by",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "opportunities", sa.Column("featured_rank", sa.Integer(), nullable=True)
    )
    op.add_column(
        "opportunities",
        sa.Column("editor_note", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "opportunities", sa.Column("review_reason", sa.String(), nullable=True)
    )
    op.execute(
        "UPDATE opportunities SET review_reason = CASE WHEN source = 'community' THEN 'new_submission' ELSE 'agent_find' END WHERE status = 'pending'"
    )
    op.execute("UPDATE opportunities SET status = 'in_review' WHERE status = 'pending'")
    op.execute(
        "UPDATE opportunities SET published_at = created_at WHERE status = 'published'"
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, title FROM opportunities ORDER BY id")
    ).all()
    import re

    used = set()
    for id, title in rows:
        base = (
            re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:250].rstrip("-")
            or "opportunity"
        )
        slug, suffix = base, 1
        while slug in used:
            suffix += 1
            slug = f"{base}-{suffix}"
        used.add(slug)
        connection.execute(
            sa.text("UPDATE opportunities SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": id},
        )
    op.alter_column("opportunities", "slug", nullable=False)
    op.alter_column("opportunities", "audience", server_default=None)
    op.alter_column("opportunities", "editor_note", server_default=None)
    op.create_unique_constraint("uq_opportunities_slug", "opportunities", ["slug"])
    op.create_index("ix_opportunities_audience", "opportunities", ["audience"])
    op.create_check_constraint(
        "ck_opportunity_status",
        "opportunities",
        "status IN ('draft','in_review','published','archived','hidden')",
    )
    op.create_check_constraint(
        "ck_opportunity_audience", "opportunities", "audience IN ('public','members')"
    )
    op.create_check_constraint(
        "ck_opportunity_review_reason",
        "opportunities",
        "review_reason IS NULL OR review_reason IN ('new_submission','agent_find','reported','source_changed')",
    )
    op.create_table(
        "opportunity_slug_history",
        sa.Column("slug", sa.String(), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.String(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_opportunity_slug_history_opportunity_id",
        "opportunity_slug_history",
        ["opportunity_id"],
    )
    op.create_table(
        "collections",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("slug", sa.String(), nullable=False, unique=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("intro", sa.Text(), nullable=False),
        sa.Column("audience", sa.String(), nullable=False),
        sa.Column("filter", sa.JSON(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("published", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "collection_items",
        sa.Column(
            "collection_id",
            sa.String(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "opportunity_id",
            sa.String(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_table(
        "site_content",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("published", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("key", "version", name="uq_site_content_version"),
    )
    op.create_table(
        "site_settings",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
    )
    op.bulk_insert(
        sa.table(
            "site_settings",
            sa.column("key", sa.String()),
            sa.column("value", sa.JSON()),
        ),
        [
            {
                "key": "agent_default",
                "value": {"status": "published", "audience": "members"},
            },
            {"key": "community_default", "value": {"status": "in_review"}},
            {"key": "auto_archive", "value": True},
            {"key": "member_scan_limits", "value": {"per_hour": 3, "per_day": 10}},
            {"key": "sweep_hours", "value": 0},
        ],
    )
    op.create_table(
        "opportunity_reports",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.String(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_opportunity_reports_opportunity_id",
        "opportunity_reports",
        ["opportunity_id"],
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("actor_email", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("ip", sa.String(), nullable=True),
    )
    for column in ("actor_id", "action", "entity_type", "entity_id"):
        op.create_index(f"ix_audit_log_{column}", "audit_log", [column])


def downgrade():
    for table in (
        "audit_log",
        "opportunity_reports",
        "site_settings",
        "site_content",
        "collection_items",
        "collections",
        "opportunity_slug_history",
    ):
        op.drop_table(table)
    for name in (
        "ck_opportunity_status",
        "ck_opportunity_audience",
        "ck_opportunity_review_reason",
    ):
        op.drop_constraint(name, "opportunities", type_="check")
    op.execute(
        "UPDATE opportunities SET status = 'pending' WHERE status IN ('draft','in_review')"
    )
    op.execute("UPDATE opportunities SET status = 'hidden' WHERE status = 'archived'")
    op.drop_index("ix_opportunities_audience", table_name="opportunities")
    op.drop_constraint("uq_opportunities_slug", "opportunities", type_="unique")
    for column in (
        "review_reason",
        "editor_note",
        "featured_rank",
        "published_by",
        "published_at",
        "slug",
        "audience",
    ):
        op.drop_column("opportunities", column)
    op.drop_column("auth_refresh_tokens", "audience")
    op.drop_constraint("ck_user_role", "users", type_="check")
    op.drop_column("users", "disabled_at")
    op.drop_column("users", "role")
