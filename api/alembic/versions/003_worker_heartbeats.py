"""worker heartbeats

Revision ID: 003
Revises: 002
Create Date: 2026-09-21 01:43:11.185410

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "003"
down_revision: str | Sequence[str] | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(), nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("worker_id"),
    )


def downgrade() -> None:
    op.drop_table("worker_heartbeats")
