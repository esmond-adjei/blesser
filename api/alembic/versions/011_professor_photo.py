"""professor photo url

Revision ID: 011_professor_photo
Revises: 010_professor_socials
Create Date: 2026-10-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "011_professor_photo"
down_revision: str | Sequence[str] | None = "010_professor_socials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("professors", sa.Column("photo_url", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("professors", "photo_url")
