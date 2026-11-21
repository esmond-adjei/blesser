"""What the member was looking at when they asked, kept on their message."""

import sqlalchemy as sa

from alembic import op

revision = "0017_assistant_context"
down_revision = "0016_scan_schedules"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("assistant_messages", sa.Column("context", sa.JSON()))


def downgrade():
    op.drop_column("assistant_messages", "context")
