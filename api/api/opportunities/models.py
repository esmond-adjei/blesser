import enum
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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.core.db import Base
from api.core.ids import new_id


class OpportunityCategory(str, enum.Enum):
    """Who the opportunity is for."""

    startup = "startup"
    research = "research"
    student = "student"


class OpportunityKind(str, enum.Enum):
    grant = "grant"
    fellowship = "fellowship"
    scholarship = "scholarship"
    accelerator = "accelerator"
    incubator = "incubator"
    competition = "competition"
    internship = "internship"
    call_for_proposals = "call_for_proposals"
    training = "training"
    conference = "conference"
    job = "job"
    other = "other"


class OpportunityStatus(str, enum.Enum):
    """Moderation state: only `published` rows are public."""

    published = "published"
    draft = "draft"
    in_review = "in_review"
    archived = "archived"
    hidden = "hidden"


class OpportunitySource(str, enum.Enum):
    agent = "agent"
    community = "community"
    staff = "staff"


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','in_review','published','archived','hidden')",
            name="ck_opportunity_status",
        ),
        CheckConstraint(
            "audience IN ('public','members')", name="ck_opportunity_audience"
        ),
        CheckConstraint(
            "review_reason IS NULL OR review_reason IN ('new_submission','agent_find','reported','source_changed')",
            name="ck_opportunity_review_reason",
        ),
    )

    slug: Mapped[str] = mapped_column(String, unique=True, default=lambda: new_id())
    audience: Mapped[str] = mapped_column(String, default="public", index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    featured_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    editor_note: Mapped[str] = mapped_column(Text, default="")
    review_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String)
    organization: Mapped[str] = mapped_column(String, default="")
    category: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(
        String, default=OpportunityKind.other.value, index=True
    )
    summary: Mapped[str] = mapped_column(Text, default="")
    eligibility: Mapped[str] = mapped_column(Text, default="")
    # Free text: "Up to USD 50,000", "Fully funded", "Equity-free".
    benefits: Mapped[str] = mapped_column(String, default="")
    # Where it runs or who may apply: "Ghana", "Accra", "Africa", "Global".
    location: Mapped[str] = mapped_column(String, default="")
    countries: Mapped[list] = mapped_column(JSON, default=list)
    requirements: Mapped[list] = mapped_column(JSON, default=list)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    # Deadline as the source wrote it, plus a schedulable copy (applications/dates.py).
    deadline: Mapped[str] = mapped_column(String, default="")
    deadline_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    # Open all year, or "applications reviewed on a rolling basis".
    rolling: Mapped[bool] = mapped_column(default=False)
    # Where to apply, and the page the facts were read from (may be the same).
    link: Mapped[str] = mapped_column(String, default="")
    source_url: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(
        String, default=OpportunityStatus.published.value, index=True
    )
    source: Mapped[str] = mapped_column(String, default=OpportunitySource.agent.value)
    # Normalized organization + title: one row per real opportunity.
    dedupe_key: Mapped[str] = mapped_column(String, unique=True)
    created_by: Mapped[str | None] = mapped_column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scan_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("scans.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Last time an agent read the source page and confirmed the facts.
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
