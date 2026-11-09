from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.core.db import Base
from api.core.ids import new_id
from api.core.time import utcnow_naive


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("kind IN ('rss','sitemap','listing')", name="ck_source_kind"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    url: Mapped[str] = mapped_column(String, unique=True)
    kind: Mapped[str] = mapped_column(String)
    category_hints: Mapped[list] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(default=True)
    proposed: Mapped[bool] = mapped_column(default=False)
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_crawl_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, index=True
    )
    crawl_requested: Mapped[bool] = mapped_column(default=False)
    etag: Mapped[str] = mapped_column(String, default="")
    last_modified: Mapped[str] = mapped_column(String, default="")
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    candidates_found: Mapped[int] = mapped_column(Integer, default=0)
    opportunities_saved: Mapped[int] = mapped_column(Integer, default=0)
    last_candidates: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)


class CrawlCandidate(Base):
    __tablename__ = "crawl_candidates"
    __table_args__ = (
        CheckConstraint(
            "status IN ('new','extracted','rejected','duplicate','closed')",
            name="ck_candidate_status",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    url: Mapped[str] = mapped_column(String, unique=True)
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String, default="")
    published_date: Mapped[date | None] = mapped_column(Date)
    category_hints: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="new", index=True)
    content_hash: Mapped[str] = mapped_column(String, default="", index=True)
    dedupe_key: Mapped[str] = mapped_column(String, default="", index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    claimed_until: Mapped[datetime | None] = mapped_column(DateTime)
    claim_token: Mapped[str | None] = mapped_column(String)
    opportunity_id: Mapped[str | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive
    )


class PageCache(Base):
    __tablename__ = "page_cache"

    url: Mapped[str] = mapped_column(String, primary_key=True)
    text: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(String, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    etag: Mapped[str] = mapped_column(String, default="")
    last_modified: Mapped[str] = mapped_column(String, default="")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class CrawlHost(Base):
    __tablename__ = "crawl_hosts"

    host: Mapped[str] = mapped_column(String, primary_key=True)
    next_request_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
