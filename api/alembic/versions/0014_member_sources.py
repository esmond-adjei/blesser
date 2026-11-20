"""Members' own sources ("My sources"), checked on a schedule."""

import sqlalchemy as sa

from alembic import op

revision = "0014_member_sources"
down_revision = "0013_member_scans"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "member_sources",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("url_key", sa.Text(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("next_check_at", sa.DateTime(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime()),
        sa.Column(
            "last_scan_id",
            sa.String(),
            sa.ForeignKey("scans.id", ondelete="SET NULL"),
        ),
        sa.Column("finds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "url_key", name="uq_member_sources_user_url"),
    )
    op.create_index("ix_member_sources_user_id", "member_sources", ["user_id"])
    op.create_index(
        "ix_member_sources_next_check_at", "member_sources", ["next_check_at"]
    )


def downgrade():
    op.drop_table("member_sources")
