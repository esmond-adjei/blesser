"""run convergence budgets

Revision ID: 002
Revises: 001
Create Date: 2026-09-21 01:42:06.315537

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "002"
down_revision: str | Sequence[str] | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("max_programs", sa.Integer(), nullable=True))
    op.add_column("runs", sa.Column("max_professors", sa.Integer(), nullable=True))
    op.add_column(
        "runs", sa.Column("max_professors_per_program", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("runs", "max_professors_per_program")
    op.drop_column("runs", "max_professors")
    op.drop_column("runs", "max_programs")
