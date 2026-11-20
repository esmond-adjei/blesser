"""Member matching: full-text search, match profiles, saved searches, alert items.

- opportunities.search_vector: a stored generated tsvector with a GIN index,
  replacing the ILIKE word search.
- match_profiles and saved_searches drive "For you" and new-match alerts.
- notifications.items lets an alert email list the listings it is about.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0009_member_matching"
down_revision = "0008_assistant"
branch_labels = None
depends_on = None

SEARCH_VECTOR_SQL = (
    "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(organization, '')), 'B') || "
    "setweight(to_tsvector('english', replace(coalesce(kind, ''), '_', ' ')), 'B') || "
    "setweight(to_tsvector('english', coalesce(tags::text, '')), 'B') || "
    "setweight(to_tsvector('english', coalesce(summary, '')), 'C') || "
    "setweight(to_tsvector('english', coalesce(location, '')), 'C') || "
    "setweight(to_tsvector('english', coalesce(eligibility, '')), 'D')"
)

ALERTS = "alerts IN ('off','daily','weekly')"


def upgrade():
    op.add_column(
        "opportunities",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(SEARCH_VECTOR_SQL, persisted=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_opportunities_search_vector",
        "opportunities",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_index("ix_opportunities_published_at", "opportunities", ["published_at"])
    op.add_column("notifications", sa.Column("items", sa.JSON(), nullable=True))

    op.create_table(
        "match_profiles",
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("kinds", sa.JSON(), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("levels", sa.JSON(), nullable=False),
        sa.Column("countries", sa.JSON(), nullable=False),
        sa.Column("alerts", sa.String(8), nullable=False),
        sa.Column("closing_soon", sa.Boolean(), nullable=False),
        sa.Column("last_alert_at", sa.DateTime(), nullable=True),
        sa.Column("last_closing_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(ALERTS, name="ck_match_profile_alerts"),
    )
    op.create_table(
        "saved_searches",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("alerts", sa.String(8), nullable=False),
        sa.Column("last_alert_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(ALERTS, name="ck_saved_search_alerts"),
    )
    op.create_index("ix_saved_searches_user_id", "saved_searches", ["user_id"])


def downgrade():
    op.drop_index("ix_saved_searches_user_id", table_name="saved_searches")
    op.drop_table("saved_searches")
    op.drop_table("match_profiles")
    op.drop_column("notifications", "items")
    op.drop_index("ix_opportunities_published_at", table_name="opportunities")
    op.drop_index("ix_opportunities_search_vector", table_name="opportunities")
    op.drop_column("opportunities", "search_vector")
