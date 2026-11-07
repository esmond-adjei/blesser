"""auth users and refresh grants

Revision ID: 012_auth_users
Revises: 011_professor_photo
Create Date: 2026-10-13

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "012_auth_users"
down_revision: str | Sequence[str] | None = "011_professor_photo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_table(
        "auth_refresh_tokens",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_auth_refresh_tokens_user_id"), "auth_refresh_tokens", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_auth_refresh_tokens_token_hash"), "auth_refresh_tokens", ["token_hash"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_auth_refresh_tokens_token_hash"), table_name="auth_refresh_tokens")
    op.drop_index(op.f("ix_auth_refresh_tokens_user_id"), table_name="auth_refresh_tokens")
    op.drop_table("auth_refresh_tokens")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
