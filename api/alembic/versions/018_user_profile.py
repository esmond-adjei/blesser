"""user profile: display name and avatar

Revision ID: 018_user_profile
Revises: 017_refresh_grants_cascade
Create Date: 2026-10-15

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "018_user_profile"
down_revision: str | Sequence[str] | None = "017_refresh_grants_cascade"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String(80), nullable=True))
    op.add_column("users", sa.Column("avatar", sa.LargeBinary(), nullable=True))
    op.add_column("users", sa.Column("avatar_key", sa.String(64), nullable=True))
    op.create_index("ix_users_avatar_key", "users", ["avatar_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_avatar_key", table_name="users")
    op.drop_column("users", "avatar_key")
    op.drop_column("users", "avatar")
    op.drop_column("users", "display_name")
