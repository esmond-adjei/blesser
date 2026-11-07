"""Scans and the DB-backed work queue their agent tasks run on."""

import enum
from datetime import datetime
from typing import ClassVar

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text, func
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
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    task_type: Mapped[str] = mapped_column(String)
    # What the task covers, e.g. "category:startup".
    target: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(TaskStatus, native_enum=False, length=16), default=TaskStatus.pending, index=True
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
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __mapper_args__: ClassVar[dict] = {"version_id_col": attempt, "version_id_generator": False}

    scan: Mapped["Scan"] = relationship(back_populates="tasks")


class WorkerHeartbeat(Base):
    """One row per live worker process."""

    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(String, primary_key=True)
    concurrency: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, index=True)
