"""usage metering rollups

Revision ID: 023_usage_daily
Revises: 022_account_exports
Create Date: 2026-10-15

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "023_usage_daily"
down_revision: str | Sequence[str] | None = "022_account_exports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usage_daily",
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("feature", sa.String(32), primary_key=True),
        sa.Column("provider", sa.String(32), primary_key=True),
        sa.Column("model", sa.String(128), primary_key=True),
        sa.Column("calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_index("ix_usage_daily_day", "usage_daily", ["day"])


def downgrade() -> None:
    op.drop_index("ix_usage_daily_day", table_name="usage_daily")
    op.drop_table("usage_daily")
