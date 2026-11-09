"""Crawler sources, candidates, shared pages and scan metrics."""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002_editorial_architecture"
branch_labels = None
depends_on = None

SEEDS = [
    ("https://wellcome.org/research-funding/schemes", "listing", ["research"]),
    ("https://www.daad-ghana.org/en/find-funding/", "listing", ["student", "research"]),
    ("https://neip.gov.gh/", "listing", ["startup"]),
    (
        "https://gcgh.grandchallenges.org/grant-opportunities",
        "listing",
        ["research", "startup"],
    ),
    ("https://www.tonyelumelufoundation.org/", "listing", ["startup"]),
    (
        "https://www.opportunitiesforafricans.com/feed/",
        "rss",
        ["startup", "research", "student"],
    ),
    ("https://opportunitydesk.org/feed/", "rss", ["startup", "research", "student"]),
]


def upgrade():
    sources = op.create_table(
        "sources",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("url", sa.String(), nullable=False, unique=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("category_hints", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("proposed", sa.Boolean(), nullable=False),
        sa.Column("last_crawled_at", sa.DateTime()),
        sa.Column("next_crawl_at", sa.DateTime(), nullable=False),
        sa.Column("crawl_requested", sa.Boolean(), nullable=False),
        sa.Column("etag", sa.String(), nullable=False),
        sa.Column("last_modified", sa.String(), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("candidates_found", sa.Integer(), nullable=False),
        sa.Column("opportunities_saved", sa.Integer(), nullable=False),
        sa.Column("last_candidates", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('rss','sitemap','listing')", name="ck_source_kind"
        ),
    )
    op.create_index("ix_sources_next_crawl_at", "sources", ["next_crawl_at"])
    op.create_table(
        "crawl_candidates",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("url", sa.String(), nullable=False, unique=True),
        sa.Column(
            "source_id", sa.String(), sa.ForeignKey("sources.id", ondelete="SET NULL")
        ),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("published_date", sa.Date()),
        sa.Column("category_hints", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("dedupe_key", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("claimed_until", sa.DateTime()),
        sa.Column("claim_token", sa.String()),
        sa.Column(
            "opportunity_id",
            sa.String(),
            sa.ForeignKey("opportunities.id", ondelete="SET NULL"),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('new','extracted','rejected','duplicate','closed')",
            name="ck_candidate_status",
        ),
    )
    for col in ("source_id", "status", "content_hash", "dedupe_key"):
        op.create_index("ix_crawl_candidates_" + col, "crawl_candidates", [col])
    op.create_table(
        "page_cache",
        sa.Column("url", sa.String(), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("etag", sa.String(), nullable=False),
        sa.Column("last_modified", sa.String(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_page_cache_expires_at", "page_cache", ["expires_at"])
    op.create_table(
        "crawl_hosts",
        sa.Column("host", sa.String(), primary_key=True),
        sa.Column("next_request_at", sa.DateTime(), nullable=False),
    )
    op.add_column(
        "scan_tasks",
        sa.Column("metrics", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.alter_column("scan_tasks", "metrics", server_default=None)
    from datetime import UTC, datetime

    now = datetime.now(UTC).replace(tzinfo=None)
    op.bulk_insert(
        sources,
        [
            {
                "id": f"seed-{i}",
                "url": url,
                "kind": kind,
                "category_hints": categories,
                "enabled": True,
                "proposed": False,
                "next_crawl_at": now,
                "crawl_requested": False,
                "etag": "",
                "last_modified": "",
                "consecutive_failures": 0,
                "last_error": "",
                "candidates_found": 0,
                "opportunities_saved": 0,
                "last_candidates": 0,
                "created_at": now,
            }
            for i, (url, kind, categories) in enumerate(SEEDS)
        ],
    )


def downgrade():
    op.drop_column("scan_tasks", "metrics")
    for name in ("crawl_hosts", "page_cache", "crawl_candidates", "sources"):
        op.drop_table(name)
