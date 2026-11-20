"""Member scans: scan kind and sites, and what each find was (new, matched, crawled)."""

import sqlalchemy as sa

from alembic import op

revision = "0013_member_scans"
down_revision = "0012_member_matching"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "scans",
        sa.Column("kind", sa.String(), nullable=False, server_default="member"),
    )
    op.add_column(
        "scans",
        sa.Column("sites", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "scan_finds",
        sa.Column("via", sa.String(), nullable=False, server_default="agent"),
    )
    op.add_column(
        "scan_finds",
        sa.Column("created", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.execute("""
        UPDATE scan_finds SET created = true
        FROM opportunities
        WHERE opportunities.id = scan_finds.opportunity_id
          AND opportunities.scan_id = scan_finds.scan_id
    """)


def downgrade():
    op.drop_column("scan_finds", "created")
    op.drop_column("scan_finds", "via")
    op.drop_column("scans", "sites")
    op.drop_column("scans", "kind")
