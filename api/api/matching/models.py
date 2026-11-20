"""What a member is looking for, and the searches they saved.

Both drive the "For you" order and the new-match alerts (matching/alerts.py).
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.core.db import Base
from api.core.ids import new_id

ALERT_CHECK = "alerts IN ('off','daily','weekly')"


class MatchProfile(Base):
    __tablename__ = "match_profiles"
    __table_args__ = (CheckConstraint(ALERT_CHECK, name="ck_match_profile_alerts"),)

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # Opportunity categories and kinds (enum values).
    categories: Mapped[list] = mapped_column(JSON, default=list)
    kinds: Mapped[list] = mapped_column(JSON, default=list)
    # Fields of study or sectors, in the member's words: "public health", "agritech".
    fields: Mapped[list] = mapped_column(JSON, default=list)
    # Stages: undergraduate, masters, phd, postdoc, founder.
    levels: Mapped[list] = mapped_column(JSON, default=list)
    # Countries they can apply from (canonical names, matching/geo.py).
    countries: Mapped[list] = mapped_column(JSON, default=list)
    # New matches: off, daily or weekly.
    alerts: Mapped[str] = mapped_column(String(8), default="daily")
    # A weekly list of good matches that close within two weeks.
    closing_soon: Mapped[bool] = mapped_column(default=True)
    # Listings published after this were not yet considered for an alert.
    last_alert_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_closing_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class SavedSearch(Base):
    """Filters plus words, with optional alerts for new listings that match."""

    __tablename__ = "saved_searches"
    __table_args__ = (CheckConstraint(ALERT_CHECK, name="ck_saved_search_alerts"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    # {q, category, kind, country, closing_within}: the list endpoint's own filters.
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    alerts: Mapped[str] = mapped_column(String(8), default="daily")
    last_alert_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
