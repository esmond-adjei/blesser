"""per-account data ownership, columns

Revision ID: 015_account_ownership
Revises: 014_provider_configs
Create Date: 2026-10-14

Nullable on purpose: existing rows are backfilled before 016 enforces NOT NULL.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "015_account_ownership"
down_revision: str | Sequence[str] | None = "014_provider_configs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OWNED_TABLES: tuple[str, ...] = (
    "runs",
    "research_tasks",
    "tool_call_logs",
    "schools",
    "programs",
    "professors",
    "papers",
    "candidate_scores",
    "email_drafts",
    "applications",
    "cv_documents",
    "cv_versions",
    "cv_branches",
    "cv_proposals",
    "assistant_conversations",
    "assistant_messages",
    "provider_configs",
    "agent_tools",
    "agent_tasks",
)


def upgrade() -> None:
    for table in OWNED_TABLES:
        op.add_column(table, sa.Column("user_id", sa.String(), nullable=True))
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])
        op.create_foreign_key(
            f"fk_{table}_user_id",
            table,
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    for table in reversed(OWNED_TABLES):
        op.drop_constraint(f"fk_{table}_user_id", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_user_id", table)
        op.drop_column(table, "user_id")
