"""Run/task infrastructure: runs, the DB-backed work queue, and traces."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.db import Base
from api.core.ids import new_id
from api.core.time import utcnow_naive

if TYPE_CHECKING:
    from api.candidates.models import CandidateScore


def status_str(status: object) -> str:
    """Columns read back as enums on some backends and plain strings on others."""
    return status.value if isinstance(status, enum.Enum) else str(status)  # type: ignore[union-attr]


class TaskStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"
    # Operator-held: neither claimable nor inflight. native_enum=False, so new members need no migration.
    paused = "paused"
    cancelled = "cancelled"
    # A lead waiting for a research slot; not inflight, so it doesn't hold the run open.
    deferred = "deferred"


#: Task statuses that still hold a run open / block duplicate queueing.
INFLIGHT_TASK_STATUSES: tuple[TaskStatus, TaskStatus] = (
    TaskStatus.pending,
    TaskStatus.running,
)

_INFLIGHT_STATUS_VALUES = frozenset(s.value for s in INFLIGHT_TASK_STATUSES)


def is_inflight_status(status: object) -> bool:
    return status_str(status) in _INFLIGHT_STATUS_VALUES


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    region: Mapped[str] = mapped_column(String)
    field: Mapped[str] = mapped_column(String)
    degree_level: Mapped[str] = mapped_column(
        String, default="phd"
    )  # "phd" | "masters" | "either"
    interest_statement: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Embedded once so scoring doesn't re-embed per professor; NULL without an embedding key.
    interest_embedding: Mapped[str | None] = mapped_column(Text, nullable=True)

    # NULL = the global default.
    max_programs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_professors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_professors_per_program: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    # JSON list of tier keys (api/prospects/tiers.py); NULL = no preference.
    school_tiers: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "system" = the system model (Auto), else a configured provider; NULL = account default.
    llm_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # JSON {task_type: "paused" | "cancelled"}; NULL = all running.
    agent_states: Mapped[str | None] = mapped_column(Text, nullable=True)
    # NULL = the built-in Standard flow.
    flow_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("agent_flows.id", ondelete="SET NULL"), nullable=True
    )
    # interest_statement keeps a copy of this document's text for readers that need it.
    interest_document_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("cv_documents.id", ondelete="SET NULL"), nullable=True
    )

    # Owner: services filter by it on every read and set it on every write.
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    tasks: Mapped[list["ResearchTask"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    candidates: Mapped[list["CandidateScore"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class ResearchTask(Base):
    """The work queue: one row per unit of agent work, claimed by workers."""

    __tablename__ = "research_tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    task_type: Mapped[str] = mapped_column(
        String, index=True
    )  # discover_programs | research_professor | research_one_professor | draft_email
    target_id: Mapped[str] = mapped_column(
        String, nullable=True, index=True
    )
    # research_one_professor targets a program (target_id) and a faculty name.
    target_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(TaskStatus, native_enum=False), default=TaskStatus.pending, index=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Python-side UTC: DB now() follows the server TimeZone, which breaks staleness checks on naive columns.
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        server_default=func.now(),
        nullable=True,
    )
    # Lease holder; claimable only once it is gone, so a resume never starts a second handler.
    claimed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    # Fencing token (ORM version column): a superseded handler's UPDATEs fail.
    attempt: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Not claimable before this (UTC); stays pending so the run stays open.
    wait_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # JSON array, one event per tool call, appended live.
    log: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_text: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    turns: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # Checkpointed every turn; a task that dies resumes from here.
    messages_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # provider/model are the last attempt's; the rest sum over attempts.
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    cache_read_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    tool_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    # "no_match" | "likely" (code-first pass), "agent" (path_reason says why), or "skipped"
    # (path_reason "run_cap" | "tail_stop").
    path: Mapped[str | None] = mapped_column(String, nullable=True)
    path_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    # created_at is queue time; durations derive from these.
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Copied from the run so isolation never needs a join.
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    __mapper_args__: ClassVar[dict] = {
        "version_id_col": attempt,
        "version_id_generator": False,
    }

    run: Mapped["Run"] = relationship(back_populates="tasks")
    tool_logs: Mapped[list["ToolCallLog"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class ToolCallLog(Base):
    """Queryable per-tool-call record; ResearchTask.log stays the cheap live-trace read."""

    __tablename__ = "tool_call_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("research_tasks.id"), index=True)
    turn: Mapped[int] = mapped_column(Integer)
    tool_name: Mapped[str] = mapped_column(String)
    input_json: Mapped[str] = mapped_column(Text, nullable=True)
    result_json: Mapped[str] = mapped_column(Text, nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    task: Mapped["ResearchTask"] = relationship(back_populates="tool_logs")


class WorkerHeartbeat(Base):
    """One row per worker process; rows older than a day are pruned."""

    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(String, primary_key=True)
    concurrency: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )
