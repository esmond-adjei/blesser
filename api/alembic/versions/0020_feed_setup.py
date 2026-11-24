"""Remember when a member finished or skipped the feed setup."""

import sqlalchemy as sa

from alembic import op

revision = "0020_feed_setup"
down_revision = "0019_check_scan_kind"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("feed_setup_at", sa.DateTime(), nullable=True))
    op.execute(
        "UPDATE users SET feed_setup_at = now() WHERE id IN (SELECT user_id FROM match_profiles)"
    )


def downgrade():
    op.drop_column("users", "feed_setup_at")
