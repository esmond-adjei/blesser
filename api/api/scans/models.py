"""Scans and the DB-backed work queue their agent tasks run on."""

import enum
from datetime import datetime
from typing import ClassVar

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.db import Base
from api.core.ids import new_id
from api.core.time import utcnow_naive


class TaskStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"
    cancelled = "cancelled"


INFLIGHT = (TaskStatus.pending, TaskStatus.running)


def status_str(status: object) -> str:
    """Columns read back as enums on some backends and plain strings on others."""
    return status.value if isinstance(status, enum.Enum) else str(status)  # type: ignore[union-attr]


class Scan(Base):
    """One request to find opportunities: a discovery task per audience category."""

    __tablename__ = "scans"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    region: Mapped[str] = mapped_column(String)
    categories: Mapped[list] = mapped_column(JSON, default=list)
    focus: Mapped[str] = mapped_column(Text, default="")
    # Listing types to look for, such as scholarship or job; empty means any.
    kinds: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    # member: a person's request; sweep: the scheduled catalogue refresh.
    kind: Mapped[str] = mapped_column(String, default="member", server_default="member")
    # Up to five public sites the member asked the agent to read first.
    sites: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    # Set on each run of a scan schedule.
    schedule_id: Mapped[str | None] = mapped_column(
        ForeignKey("scan_schedules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # running | done | cancelled
    status: Mapped[str] = mapped_column(String, default="running", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, server_default=func.now()
    )

    tasks: Mapped[list["ScanTask"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan", passive_deletes=True
    )


class ScanTask(Base):
    """The work queue: one row per unit of agent work, claimed by workers."""

    __tablename__ = "scan_tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(
        ForeignKey("scans.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    task_type: Mapped[str] = mapped_column(String)
    # What the task covers, e.g. "category:startup".
    target: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(TaskStatus, native_enum=False, length=16),
        default=TaskStatus.pending,
        index=True,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Python-side UTC: staleness checks compare against utcnow_naive().
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Lease holder: claimable only once it is gone, so a task never runs twice.
    claimed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    # Fencing token (ORM version column): a superseded handler's UPDATEs fail.
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    # JSON array, one event per model turn or tool call, appended live.
    log: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    turns: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Checkpointed every turn; a task that dies resumes from here.
    messages_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __mapper_args__: ClassVar[dict] = {
        "version_id_col": attempt,
        "version_id_generator": False,
    }

    scan: Mapped["Scan"] = relationship(back_populates="tasks")


class WorkerHeartbeat(Base):
    """One row per live worker process."""

    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(String, primary_key=True)
    concurrency: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, index=True
    )


class ScanFind(Base):
    __tablename__ = "scan_finds"

    scan_id: Mapped[str] = mapped_column(
        ForeignKey("scans.id", ondelete="CASCADE"), primary_key=True
    )
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    found_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    source_url: Mapped[str | None] = mapped_column(Text)
    # agent: saved or confirmed from the web; crawler: the pipeline; catalog: an
    # existing listing the agent matched to the member's request.
    via: Mapped[str] = mapped_column(String, default="agent", server_default="agent")
    # This scan created the listing (it was not in the catalogue before).
    created: Mapped[bool] = mapped_column(default=False, server_default="false")
    # An existing listing this scan read again and refreshed with new facts.
    updated: Mapped[bool] = mapped_column(default=False, server_default="false")


class MemberSource(Base):
    """A site a member wants checked for opportunities on a schedule ("My sources").

    Private to the member, and kept apart from the staff `sources` registry. Checks
    run as scans of kind `sources`; a domain that yields saves still becomes a staff
    source proposal through the usual agent save path.
    """

    __tablename__ = "member_sources"
    __table_args__ = (
        UniqueConstraint("user_id", "url_key", name="uq_member_sources_user_url"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(Text)
    url_key: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String)
    note: Mapped[str] = mapped_column(Text, default="")
    paused: Mapped[bool] = mapped_column(default=False)
    next_check_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, index=True
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_scan_id: Mapped[str | None] = mapped_column(
        ForeignKey("scans.id", ondelete="SET NULL")
    )
    finds: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)


class ScanSchedule(Base):
    """A scan request that repeats: each run is an ordinary scan with `schedule_id` set.

    Member schedules belong to the member and run weekly as scans of kind `scheduled`.
    Staff schedules have no owner: they run as the scheduled scans account (see
    `schedules.run_as_staff`), as scans of kind `sweep`, so the crawler pipeline runs
    first. The catalogue sweep is the first staff schedule.
    """

    __tablename__ = "scan_schedules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    # member | staff
    audience: Mapped[str] = mapped_column(String(8), default="member")
    # The member who owns it; None for staff schedules.
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(80), default="")
    categories: Mapped[list] = mapped_column(JSON, default=list)
    region: Mapped[str] = mapped_column(String(120), default="")
    focus: Mapped[str] = mapped_column(Text, default="")
    kinds: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    sites: Mapped[list] = mapped_column(JSON, default=list)
    interval_hours: Mapped[int] = mapped_column(Integer, default=168)
    paused: Mapped[bool] = mapped_column(default=False)
    # Why it paused itself: empty (runs found nothing) or inactive (owner away).
    pause_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, index=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_scan_id: Mapped[str | None] = mapped_column(
        ForeignKey("scans.id", ondelete="SET NULL", use_alter=True), nullable=True
    )
    runs: Mapped[int] = mapped_column(Integer, default=0)
    # Finished runs in a row that found nothing.
    empty_runs: Mapped[int] = mapped_column(Integer, default=0)
    # The owner last created, edited or resumed it; counts as activity.
    touched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
