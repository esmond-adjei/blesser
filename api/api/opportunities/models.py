import enum
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    event,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, deferred, mapped_column

from api.core.db import Base
from api.core.ids import new_id

#: Full-text document for search and matching. Title weighs most, then the funder,
#: kind and tags, then the summary and place, then eligibility. Kept by Postgres.
SEARCH_VECTOR_SQL = (
    "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(organization, '')), 'B') || "
    "setweight(to_tsvector('english', replace(coalesce(kind, ''), '_', ' ')), 'B') || "
    "setweight(to_tsvector('english', coalesce(tags::text, '')), 'B') || "
    "setweight(to_tsvector('english', coalesce(summary, '')), 'C') || "
    "setweight(to_tsvector('english', coalesce(location, '')), 'C') || "
    "setweight(to_tsvector('english', coalesce(eligibility, '')), 'D')"
)


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
        Index(
            "ix_opportunities_search_vector",
            "search_vector",
            postgresql_using="gin",
        ),
        Index("ix_opportunities_published_at", "published_at"),
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
    source_url: Mapped[str] = mapped_column(String, default="", index=True)
    # normalized_url() of link and source_url, kept in step by the hooks below.
    link_key: Mapped[str] = mapped_column(String, default="", index=True)
    source_url_key: Mapped[str] = mapped_column(String, default="", index=True)
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
    # Scheduled re-checks (freshness.py): when the source was last looked at, what
    # that found, and the page's content hash when the facts were last confirmed.
    checked_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    check_outcome: Mapped[str] = mapped_column(String, default="", server_default="")
    source_hash: Mapped[str] = mapped_column(String, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    # Never loaded with the row: only queries read it (service.search_clause).
    search_vector: Mapped[str] = deferred(
        mapped_column(TSVECTOR, Computed(SEARCH_VECTOR_SQL, persisted=True))
    )


# Possible-duplicate search (dedupe.possible_duplicates) uses pg_trgm on titles.
Index(
    "ix_opportunities_title_trgm",
    func.lower(Opportunity.title).label("lower_title"),
    postgresql_using="gin",
    postgresql_ops={"lower_title": "gin_trgm_ops"},
)


class OrganizationAlias(Base):
    """Maps an organization's other name to one canonical name for the dedupe key.

    Both columns hold `dedupe.organization_key` output: lowercase, no punctuation,
    without "the" or trailing words such as "foundation" and "trust".
    """

    __tablename__ = "organization_aliases"

    alias: Mapped[str] = mapped_column(String, primary_key=True)
    canonical: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DuplicateDismissal(Base):
    """A pair staff confirmed are different opportunities; first_id < second_id."""

    __tablename__ = "duplicate_dismissals"
    __table_args__ = (
        CheckConstraint("first_id < second_id", name="ck_duplicate_dismissal_order"),
    )

    first_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True
    )
    second_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True
    )
    dismissed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def url_keys(link: str, source_url: str) -> tuple[str, str]:
    from api.opportunities.page_content import normalized_url

    return (
        normalized_url(link) if link else "",
        normalized_url(source_url) if source_url else "",
    )


@event.listens_for(Opportunity, "before_insert")
@event.listens_for(Opportunity, "before_update")
def _sync_url_keys(_mapper, _connection, target: Opportunity) -> None:
    target.link_key, target.source_url_key = url_keys(
        target.link or "", target.source_url or ""
    )
