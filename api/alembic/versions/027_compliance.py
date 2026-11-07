"""compliance: sign-up consent and professor opt-outs

Revision ID: 027_compliance
Revises: 026_task_lease
Create Date: 2026-10-15

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "027_compliance"
down_revision: str | Sequence[str] | None = "026_task_lease"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("terms_accepted_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("terms_version", sa.String(32), nullable=True))
    op.create_table(
        "professor_optouts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("openalex_id", sa.String(), nullable=True, index=True),
        sa.Column("name_key", sa.String(), nullable=True, index=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("professor_optouts")
    op.drop_column("users", "terms_version")
    op.drop_column("users", "terms_accepted_at")
