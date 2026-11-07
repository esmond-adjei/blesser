"""account data exports

Revision ID: 022_account_exports
Revises: 021_user_identities
Create Date: 2026-10-15

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "022_account_exports"
down_revision: str | Sequence[str] | None = "021_user_identities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_exports",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("account_exports")
