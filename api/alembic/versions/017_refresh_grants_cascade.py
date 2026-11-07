"""refresh grants cascade on account deletion

Revision ID: 017_refresh_grants_cascade
Revises: 016_account_ownership_enforce
Create Date: 2026-10-14

"""

from collections.abc import Sequence

from alembic import op

revision: str = "017_refresh_grants_cascade"
down_revision: str | Sequence[str] | None = "016_account_ownership_enforce"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "auth_refresh_tokens_user_id_fkey", "auth_refresh_tokens", type_="foreignkey"
    )
    op.create_foreign_key(
        "auth_refresh_tokens_user_id_fkey",
        "auth_refresh_tokens",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "auth_refresh_tokens_user_id_fkey", "auth_refresh_tokens", type_="foreignkey"
    )
    op.create_foreign_key(
        "auth_refresh_tokens_user_id_fkey",
        "auth_refresh_tokens",
        "users",
        ["user_id"],
        ["id"],
    )
