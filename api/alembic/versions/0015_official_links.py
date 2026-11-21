"""Official links for aggregator finds: where a listing was found, and a review reason.

`found_via_url` keeps the aggregator post a listing came from (staff only), so the same
post is not processed twice. `official_checked_at` paces the backfill that moves
existing listings off aggregator pages. `no_official_link` holds a find whose official
page could not be found for staff review.
"""

import sqlalchemy as sa

from alembic import op

revision = "0015_official_links"
down_revision = "0014_member_sources"
branch_labels = None
depends_on = None

_OLD = "'new_submission','agent_find','reported','source_changed'"
_NEW = _OLD + ",'no_official_link'"


def upgrade():
    op.add_column(
        "opportunities",
        sa.Column("found_via_url", sa.String(), server_default="", nullable=False),
    )
    op.add_column("opportunities", sa.Column("official_checked_at", sa.DateTime()))
    op.create_index(
        "ix_opportunities_found_via_url", "opportunities", ["found_via_url"]
    )
    op.drop_constraint("ck_opportunity_review_reason", "opportunities", type_="check")
    op.create_check_constraint(
        "ck_opportunity_review_reason",
        "opportunities",
        f"review_reason IS NULL OR review_reason IN ({_NEW})",
    )


def downgrade():
    op.execute(
        "UPDATE opportunities SET review_reason = 'source_changed' "
        "WHERE review_reason = 'no_official_link'"
    )
    op.drop_constraint("ck_opportunity_review_reason", "opportunities", type_="check")
    op.create_check_constraint(
        "ck_opportunity_review_reason",
        "opportunities",
        f"review_reason IS NULL OR review_reason IN ({_OLD})",
    )
    op.drop_index("ix_opportunities_found_via_url", table_name="opportunities")
    op.drop_column("opportunities", "official_checked_at")
    op.drop_column("opportunities", "found_via_url")
