"""run model: runs.llm_provider

Revision ID: 030_run_llm_provider
Revises: 029_school_institution
Create Date: 2026-10-16

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "030_run_llm_provider"
down_revision: str | Sequence[str] | None = "029_school_institution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("llm_provider", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "llm_provider")
