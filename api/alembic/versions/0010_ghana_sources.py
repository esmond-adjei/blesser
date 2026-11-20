"""More Ghana crawler sources: government, universities and funders.

Each enabled source was read on 20 November 2026 and listed current calls,
scholarships or grants, with robots.txt allowing the listing path for all
agents (the Japan embassy's robots.txt could not be read; the crawler checks it
again before every fetch). The two disabled sources are official Ghana
agencies whose pages were stale or unreachable to robots checks on that date;
staff can enable them from the Sources page once they post new calls.
"""

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "0010_ghana_sources"
down_revision = "0009_crawler_freshness"
branch_labels = None
depends_on = None

# (id, url, kind, category hints, enabled)
SOURCES = [
    (
        "ghana-scholarships-authority",
        "https://scholarships.gov.gh/opportunities",
        "listing",
        ["student"],
        True,
    ),
    (
        "ug-research-calls",
        "https://rid.ug.edu.gh/call-for-applications",
        "listing",
        ["research", "student"],
        True,
    ),
    (
        "ug-announcements",
        "https://ug.edu.gh/announcements",
        "listing",
        ["student", "research"],
        True,
    ),
    (
        "ug-financial-aid",
        "https://www.ug.edu.gh/financialaid/",
        "listing",
        ["student"],
        True,
    ),
    (
        "knust-announcements",
        "https://www.knust.edu.gh/announcements",
        "listing",
        ["student", "research"],
        True,
    ),
    (
        "aref-funding-calls",
        "https://africaresearchexcellencefund.org.uk/funding-calls",
        "listing",
        ["research"],
        True,
    ),
    (
        "japan-embassy-ghana",
        "https://www.gh.emb-japan.go.jp/itpr_en/index.html",
        "listing",
        ["student", "research"],
        True,
    ),
    (
        "great-scholarships-ghana",
        "https://study-uk.britishcouncil.org/scholarships-funding/great-scholarships/ghana",
        "listing",
        ["student"],
        True,
    ),
    (
        "gea-expressions-of-interest",
        "https://gea.gov.gh/category/expression-of-interest/",
        "listing",
        ["startup"],
        False,
    ),
    (
        "getfund-scholarships",
        "https://www.getfund.gov.gh/service/scholarship-programme/",
        "listing",
        ["student"],
        False,
    ),
]

_sources = sa.table(
    "sources",
    sa.column("id", sa.String),
    sa.column("url", sa.String),
    sa.column("kind", sa.String),
    sa.column("category_hints", sa.JSON),
    sa.column("enabled", sa.Boolean),
    sa.column("proposed", sa.Boolean),
    sa.column("next_crawl_at", sa.DateTime),
    sa.column("crawl_requested", sa.Boolean),
    sa.column("etag", sa.String),
    sa.column("last_modified", sa.String),
    sa.column("consecutive_failures", sa.Integer),
    sa.column("last_error", sa.Text),
    sa.column("candidates_found", sa.Integer),
    sa.column("opportunities_saved", sa.Integer),
    sa.column("last_candidates", sa.Integer),
    sa.column("created_at", sa.DateTime),
)


def upgrade():
    from sqlalchemy.dialects.postgresql import insert

    now = datetime.now(UTC).replace(tzinfo=None)
    rows = [
        {
            "id": "seed-" + key,
            "url": url,
            "kind": kind,
            "category_hints": categories,
            "enabled": enabled,
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
        for key, url, kind, categories, enabled in SOURCES
    ]
    # Staff may already have added one of these by hand: keep their row.
    op.execute(
        insert(_sources).values(rows).on_conflict_do_nothing(index_elements=["url"])
    )


def downgrade():
    op.execute(
        _sources.delete().where(
            _sources.c.id.in_(["seed-" + key for key, *_ in SOURCES])
        )
    )
