"""professor bio with source

Revision ID: 009_professor_bio
Revises: 008_professor_lab_name
Create Date: 2026-10-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "009_professor_bio"
down_revision: str | Sequence[str] | None = "008_professor_lab_name"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("professors", sa.Column("bio", sa.Text(), nullable=True))
    op.add_column("professors", sa.Column("bio_source", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("professors", "bio_source")
    op.drop_column("professors", "bio")
