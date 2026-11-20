"""Store normalized opportunity URLs so duplicate checks are one indexed lookup."""

import sqlalchemy as sa

from alembic import op

revision = "0009_crawler_freshness"
down_revision = "0008_assistant"
branch_labels = None
depends_on = None


def upgrade():
    from api.opportunities.models import url_keys

    for column in ("link_key", "source_url_key"):
        op.add_column(
            "opportunities",
            sa.Column(column, sa.String(), nullable=False, server_default=""),
        )
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, link, source_url FROM opportunities"))
    for row_id, link, source_url in rows.all():
        link_key, source_key = url_keys(link or "", source_url or "")
        bind.execute(
            sa.text(
                "UPDATE opportunities SET link_key = :link, source_url_key = :source"
                " WHERE id = :id"
            ),
            {"link": link_key, "source": source_key, "id": row_id},
        )
    op.create_index("ix_opportunities_link_key", "opportunities", ["link_key"])
    op.create_index(
        "ix_opportunities_source_url_key", "opportunities", ["source_url_key"]
    )


def downgrade():
    op.drop_index("ix_opportunities_source_url_key", "opportunities")
    op.drop_index("ix_opportunities_link_key", "opportunities")
    op.drop_column("opportunities", "source_url_key")
    op.drop_column("opportunities", "link_key")
