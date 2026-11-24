"""The listing types a scan looks for, such as scholarships or jobs."""

import sqlalchemy as sa

from alembic import op

revision = "0018_scan_kinds"
down_revision = "0017_assistant_context"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("scans", "scan_schedules"):
        op.add_column(
            table, sa.Column("kinds", sa.JSON(), nullable=False, server_default="[]")
        )


def downgrade():
    for table in ("scans", "scan_schedules"):
        op.drop_column(table, "kinds")
