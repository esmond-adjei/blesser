from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from api.core.db import Base
from api.core.ids import new_id


class SlugHistory(Base):
    __tablename__ = "opportunity_slug_history"

    slug: Mapped[str] = mapped_column(String, primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String, unique=True)
    title: Mapped[str] = mapped_column(String)
    intro: Mapped[str] = mapped_column(Text, default="")
    audience: Mapped[str] = mapped_column(String, default="public")
    filter: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    published: Mapped[bool] = mapped_column(default=False)


class CollectionItem(Base):
    __tablename__ = "collection_items"

    collection_id: Mapped[str] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True
    )
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)


class SiteContent(Base):
    __tablename__ = "site_content"
    __table_args__ = (
        UniqueConstraint("key", "version", name="uq_site_content_version"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer)
    value: Mapped[dict] = mapped_column(JSON)
    published: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class SiteSetting(Base):
    __tablename__ = "site_settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict | bool | int | str] = mapped_column(JSON)


class OpportunityReport(Base):
    __tablename__ = "opportunity_reports"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    reason: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    resolved: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(String, index=True)
    actor_email: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String, index=True)
    entity_type: Mapped[str] = mapped_column(String, index=True)
    entity_id: Mapped[str] = mapped_column(String, index=True)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    at: Mapped[datetime] = mapped_column(server_default=func.now())
    ip: Mapped[str | None] = mapped_column(String, nullable=True)
