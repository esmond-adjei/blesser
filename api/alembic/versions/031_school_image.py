"""schools.image_url

Revision ID: 031_school_image
Revises: 030_run_llm_provider
Create Date: 2026-10-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "031_school_image"
down_revision: str | Sequence[str] | None = "030_run_llm_provider"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("schools", sa.Column("image_url", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("schools", "image_url")
