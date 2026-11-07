"""professor social links

Revision ID: 010_professor_socials
Revises: 009_professor_bio
Create Date: 2026-10-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "010_professor_socials"
down_revision: str | Sequence[str] | None = "009_professor_bio"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "professors",
        sa.Column("socials", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("professors", "socials")
