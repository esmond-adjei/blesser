"""professor lab affiliation

Revision ID: 008_professor_lab_name
Revises: 536daf3da970
Create Date: 2026-10-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "008_professor_lab_name"
down_revision: str | Sequence[str] | None = "536daf3da970"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("professors", sa.Column("lab_name", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("professors", "lab_name")
