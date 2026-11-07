"""third-party sign-in identities

Revision ID: 021_user_identities
Revises: 020_email_tokens
Create Date: 2026-10-15

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "021_user_identities"
down_revision: str | Sequence[str] | None = "020_email_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_identities",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "provider", "subject", name="uq_user_identities_provider_subject"
        ),
    )


def downgrade() -> None:
    op.drop_table("user_identities")
