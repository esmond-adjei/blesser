"""Queue mechanics: claiming, event sink, checkpoints, reaper, loops. Handlers live with their feature."""

import asyncio
import contextvars
import json
import os
import random
import socket
import traceback
import uuid
from datetime import UTC, timedelta

import asyncpg
from sqlalchemy import and_, case, delete, func, literal, not_, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.orm.exc import StaleDataError

from api.agent.llm.base import is_transient
from api.agent.orchestrator import (
    ALLOWANCE_PAUSE_PREFIX,
    ModelAllowanceRefused,
    TaskHalted,
    task_usage,
)
from api.core.config import settings
from api.core.db import SessionLocal, listener_dsn
from api.core.egress import public_error
from api.core.time import utcnow_naive
from api.outreach.tasks import run_draft_email
from api.prospects.openalex import OpenAlexWait
from api.prospects.tasks import (
    run_discover_programs,
    run_research_one_professor,
    run_research_professor,
)
from api.runs import models as run_models
from api.runs.agents import OUTLIVES_RUN_HALT
from api.runs.lifecycle import note_tasks_drained
from api.runs.notify import CHANNEL, notify_tasks, notify_work, parse_payload

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
HEARTBEAT_TTL = timedelta(days=1)

# Tests import queue._utcnow.
_utcnow = utcnow_naive

#: (task_id, attempt) this coroutine runs, so dispatch can refuse work once it is halted (current_lease_halt).
current_lease: contextvars.ContextVar[tuple[str, int] | None] = contextvars.ContextVar(
    "current_lease", default=None
)


def heartbeat_stale_after() -> timedelta:
    """Heartbeat age past which a worker is gone (same 4x rule as the health view)."""
    return timedelta(seconds=max(settings.worker_heartbeat_seconds, 1) * 4)


def _live_worker_ids():
    return select(run_models.WorkerHeartbeat.worker_id).where(
        run_models.WorkerHeartbeat.last_seen_at
        >= utcnow_naive() - heartbeat_stale_after()
    )


async def current_lease_halt(session) -> str | None:
    """Why the running attempt must stop, or None; read fresh every tool batch."""
    lease = current_lease.get()
    if lease is None:
        return None
    task_id, attempt = lease
    row = (
        await session.execute(
            select(
                run_models.ResearchTask.status, run_models.ResearchTask.attempt
            ).where(run_models.ResearchTask.id == task_id)
        )
    ).one_or_none()
    if row is None:
        return "deleted"
    status = run_models.status_str(row.status)
    if row.attempt != attempt:
        return "superseded"
    if status != run_models.TaskStatus.running.value:
        return status
    return None


async def heartbeat(session, worker_id: str = WORKER_ID, concurrency: int = 1) -> None:
    now = utcnow_naive()
    row = await session.get(run_models.WorkerHeartbeat, worker_id)
    if row is None:
        session.add(
            run_models.WorkerHeartbeat(
                worker_id=worker_id,
                concurrency=concurrency,
                started_at=now,
                last_seen_at=now,
            )
        )
    else:
        row.concurrency = concurrency
        row.last_seen_at = now
    await session.commit()


async def retire_heartbeat(worker_id: str = WORKER_ID) -> None:
    """So health reports "no live worker" at once instead of after the staleness window."""
    try:
        async with SessionLocal() as session:
            await session.execute(
                delete(run_models.WorkerHeartbeat).where(
                    run_models.WorkerHeartbeat.worker_id == worker_id
                )
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001 - best effort; staleness covers it
        print(f"[worker] heartbeat retire failed: {exc}", flush=True)


async def prune_heartbeats(session, older_than: timedelta = HEARTBEAT_TTL) -> int:
    result = await session.execute(
        delete(run_models.WorkerHeartbeat).where(
            run_models.WorkerHeartbeat.last_seen_at < utcnow_naive() - older_than
        )
    )
    await session.commit()
    return result.rowcount


def _preview(value: object, limit: int = 100) -> str:
    if isinstance(value, dict) and value:
        value = next(iter(value.values()))

    text = value if isinstance(value, str) else json.dumps(value, default=str)
    text = " ".join(text.split())

    return text if len(text) <= limit else text[:limit] + "..."


def _make_event_sink(session, task: run_models.ResearchTask, label: str):
    """on_event callback that persists the growing trace on the task row for live progress."""
    events: list[dict] = []
    existing_log = task.log
    if existing_log:
        try:
            loaded = json.loads(existing_log)
            if isinstance(loaded, list):
                events = loaded
        except (json.JSONDecodeError, TypeError):
            events = []

    async def on_event(event: dict) -> None:
        # task.log keeps only the preview; copy, since the caller's dict must stay intact.
        full_result = event.get("result")
        trace_event = {k: v for k, v in event.items() if k != "result"}
        # Lets the UI say how long the model has been thinking since.
        trace_event["at"] = utcnow_naive().isoformat() + "Z"
        events.append(trace_event)
        if trace_event.get("kind") == "turn":
            print(
                f"[worker] [{label} turn {trace_event['turn']}] "
                f"thinking: {_preview(trace_event.get('note') or '')}",
                flush=True,
            )
            task.log = json.dumps(events)
            await notify_tasks(session, task.run_id)
            await session.commit()
            return
        status = "ok" if trace_event.get("ok") else "ERROR"
        print(
            f"[worker] [{label} turn {trace_event['turn']}] "
            f"{trace_event['tool']}({_preview(trace_event['input'])}) -> {status}",
            flush=True,
        )
        task.log = json.dumps(events)
        result_json = json.dumps(full_result, default=str)
        # Stored whole; only a pathological payload is capped, as a valid JSON envelope.
        cap = settings.tool_log_max_chars
        if cap > 0 and len(result_json) > cap:
            result_json = json.dumps(
                {"truncated": True, "chars": len(result_json), "preview": result_json[:cap]}
            )
        session.add(
            run_models.ToolCallLog(
                task_id=task.id,
                user_id=task.user_id,
                turn=trace_event["turn"],
                tool_name=trace_event["tool"],
                input_json=json.dumps(trace_event.get("input"), default=str),
                result_json=result_json,
                ok=bool(trace_event.get("ok")),
            )
        )
        await notify_tasks(session, task.run_id)
        await session.commit()

    return on_event


def _running_in_run(narrow_only: bool = False):
    """Correlated count of running tasks in the candidate task's run."""
    other = aliased(run_models.ResearchTask)
    conditions = [
        other.run_id == run_models.ResearchTask.run_id,
        other.status == run_models.TaskStatus.running,
    ]
    if narrow_only:
        conditions.append(other.task_type == "research_one_professor")
    return (
        select(func.count()).select_from(other).where(*conditions).scalar_subquery()
    )


def _stage_priority():
    # Drafts first; then a run's first narrow task jumps the supervisors so the first match
    # arrives early; then discovery and supervisors; the narrow bulk last.
    return case(
        (run_models.ResearchTask.task_type == "draft_email", 0),
        (
            and_(
                run_models.ResearchTask.task_type == "research_one_professor",
                _running_in_run(narrow_only=True) == 0,
            ),
            1,
        ),
        (
            run_models.ResearchTask.task_type.in_(
                ["discover_programs", "research_professor"]
            ),
            2,
        ),
        else_=3,
    )


async def _claim_next_task(
    session, run_id: str | list[str] | None = None
) -> run_models.ResearchTask | None:
    """Claim the next pending task (run_ids is a test seam)."""
    query = (
        select(run_models.ResearchTask)
        .join(run_models.Run, run_models.ResearchTask.run_id == run_models.Run.id)
        .where(
            run_models.ResearchTask.status == run_models.TaskStatus.pending,
            or_(
                run_models.Run.status == "running",
                run_models.ResearchTask.task_type.in_(OUTLIVES_RUN_HALT),
            ),
            # Not while an earlier attempt is still live; it releases the lease at conclude.
            or_(
                run_models.ResearchTask.claimed_by.is_(None),
                run_models.ResearchTask.claimed_by.not_in(_live_worker_ids()),
            ),
            # runs.agent_states is JSON keyed by task type.
            or_(
                run_models.Run.agent_states.is_(None),
                not_(
                    run_models.Run.agent_states.contains(
                        literal('"') + run_models.ResearchTask.task_type + literal('"')
                    )
                ),
            ),
            or_(
                run_models.ResearchTask.wait_until.is_(None),
                run_models.ResearchTask.wait_until <= utcnow_naive(),
            ),
        )
        # Fewest running first, so one large run can't hold every loop.
        .order_by(
            _stage_priority(), _running_in_run(), run_models.ResearchTask.created_at
        )
        .limit(1)
    )
    if isinstance(run_id, list):
        query = query.where(run_models.ResearchTask.run_id.in_(run_id))
    elif run_id is not None:
        query = query.where(run_models.ResearchTask.run_id == run_id)
    # OF limits locking to task rows; otherwise the joined run row locks and same-run claims serialize.
    query = query.with_for_update(skip_locked=True, of=run_models.ResearchTask)
    result = await session.execute(query)
    task = result.scalar_one_or_none()
    if task:
        task.status = run_models.TaskStatus.running
        task.started_at = utcnow_naive()
        task.claimed_by = WORKER_ID
        task.attempt = (task.attempt or 0) + 1
        task.wait_until = None
        # Notifying the claim is what lets the feed's sweep interval be slow.
        await notify_tasks(session, task.run_id)
        await session.commit()
    return task


async def reap_stale_tasks(session, stale_after_minutes: int | None = None) -> int:
    """Requeue running tasks whose claimer's heartbeat is stale or gone.

    A slow but live attempt is never reaped, so a task can't run twice. Rows with no
    claimer fall back to the updated_at TTL.
    """
    if stale_after_minutes is None:
        stale_after_minutes = settings.stale_task_minutes
    cutoff = utcnow_naive() - timedelta(minutes=stale_after_minutes)
    task = run_models.ResearchTask
    result = await session.execute(
        select(task).where(
            task.status == run_models.TaskStatus.running,
            or_(
                and_(
                    task.claimed_by.is_(None),
                    func.coalesce(task.updated_at, task.created_at) < cutoff,
                ),
                and_(
                    task.claimed_by.is_not(None),
                    task.claimed_by.not_in(_live_worker_ids()),
                ),
            ),
        )
    )
    tasks = result.scalars().all()
    for row in tasks:
        row.status = run_models.TaskStatus.pending
        row.started_at = None
        row.claimed_by = None
    for run_id in {t.run_id for t in tasks}:
        await notify_tasks(session, run_id)
        await notify_work(session, run_id)
    await session.commit()
    return len(tasks)


TASK_HANDLERS = {
    "discover_programs": run_discover_programs,
    "research_professor": run_research_professor,
    "research_one_professor": run_research_one_professor,
    "draft_email": run_draft_email,
}


async def _mid_run_mark(
    session, task: run_models.ResearchTask, label: str
) -> str | None:
    """The paused/cancelled mark placed mid-run, else None.

    Refreshes only the status column, so uncommitted handler writes survive.
    """
    await session.refresh(task, attribute_names=["status"])
    status = run_models.status_str(task.status)
    if status != run_models.TaskStatus.running.value:
        print(
            f"[worker] {label} marked {status} mid-run; honoring the mark", flush=True
        )
        return status
    return None


async def process_one() -> bool:
    async with SessionLocal() as session:
        task = await _claim_next_task(session)
        if task is None:
            return False
        task_id, attempt = task.id, task.attempt
        token = current_lease.set((task_id, attempt))
        try:
            return await _process_claimed(session, task)
        except StaleDataError:
            # Fenced out: a newer attempt owns the row.
            await session.rollback()
            print(
                f"[worker] task {task_id[:8]} attempt {attempt} superseded", flush=True
            )
            return True
        finally:
            current_lease.reset(token)
            await _release_lease(task_id, attempt)


async def _release_lease(task_id: str, attempt: int) -> None:
    """Drop this attempt's claim (fenced), and wake loops for a task resumed meanwhile."""
    from sqlalchemy import update

    try:
        async with SessionLocal() as session:
            table = run_models.ResearchTask.__table__
            result = await session.execute(
                update(table)
                .where(table.c.id == task_id, table.c.attempt == attempt)
                .values(claimed_by=None)
                .returning(table.c.status, table.c.run_id)
            )
            row = result.one_or_none()
            if row is not None and run_models.status_str(row.status) == "pending":
                await notify_work(session, row.run_id)
            await session.commit()
    except Exception as exc:  # noqa: BLE001 - the reaper frees it if this fails
        print(f"[worker] lease release failed for {task_id[:8]}: {exc}", flush=True)


async def _superseded(session, task_id: str, attempt: int) -> bool:
    """After a rollback the ORM reloads the current attempt, so the version fence no longer protects us."""
    current = (
        await session.execute(
            select(run_models.ResearchTask.attempt).where(
                run_models.ResearchTask.id == task_id
            )
        )
    ).scalar_one_or_none()
    return current != attempt


def _charge(task: run_models.ResearchTask, usage: dict) -> None:
    """Accumulate an attempt's tokens and record the turns it reached."""
    task.input_tokens = (task.input_tokens or 0) + usage.get("input_tokens", 0)
    task.output_tokens = (task.output_tokens or 0) + usage.get("output_tokens", 0)
    if usage.get("turns"):
        task.turns = usage["turns"]
    _record_metrics(task, usage)


def _record_metrics(task: run_models.ResearchTask, usage: dict) -> None:
    for key in ("cache_read_tokens", "model_seconds", "tool_seconds"):
        if usage.get(key):
            setattr(task, key, (getattr(task, key) or 0) + usage[key])
    for key in ("provider", "model", "path", "path_reason"):
        if key in usage:
            setattr(task, key, usage[key])


async def _park_for_allowance(
    session, task: run_models.ResearchTask, run_id: str, reason: str
) -> None:
    """Out of allowance: park the task and pause the run, so queued work isn't claimed only to be refused."""
    from sqlalchemy import update

    from api.notifications import events as notification_events

    task.status = run_models.TaskStatus.paused
    task.claimed_by = None
    task.error = f"{ALLOWANCE_PAUSE_PREFIX}{reason}"
    # Conditional flip so exactly one of several concurrent refusals notifies.
    flipped = (
        await session.execute(
            update(run_models.Run)
            .where(run_models.Run.id == run_id, run_models.Run.status == "running")
            .values(status="paused")
            .returning(run_models.Run.id)
        )
    ).scalar_one_or_none()
    if flipped is not None:
        run = await session.get(run_models.Run, run_id)
        if run is not None:
            await notification_events.run_paused(session, run, task.id, task.attempt or 0)
    await notify_tasks(session, run_id)
    await session.commit()


async def _honor_halt(session, task: run_models.ResearchTask, run_id: str, reason: str) -> None:
    """A halted run requeues the task, a paused agent parks it, a cancelled agent ends it."""
    from api.runs import agents

    if reason == f"agent {agents.CANCELLED}":
        task.status = run_models.TaskStatus.cancelled
        task.error = agents.CANCELLED_NOTE
        task.finished_at = utcnow_naive()
    elif reason == f"agent {agents.PAUSED}":
        task.status = run_models.TaskStatus.paused
    else:
        task.status = run_models.TaskStatus.pending
        task.started_at = None
    await notify_tasks(session, run_id)
    await note_tasks_drained(session, run_id)
    await session.commit()


OPENALEX_WAIT_PREFIX = "Waiting for OpenAlex: "


async def _wait_for_openalex(
    session, task: run_models.ResearchTask, run_id: str, wait: OpenAlexWait
) -> None:
    """Requeue until OpenAlex is usable, so no tokens go on a professor that can't be verified.

    Resumes are spread out so waiting tasks don't all start in the same second.
    """
    spread = max(0, settings.openalex_resume_spread_seconds)
    if wait.reason == "auth":
        spread = min(spread, max(0, settings.openalex_auth_recheck_seconds))
    resume = wait.until.astimezone(UTC).replace(tzinfo=None) + timedelta(
        seconds=random.uniform(0, spread)
    )
    task.status = run_models.TaskStatus.pending
    task.started_at = None
    task.claimed_by = None
    task.wait_until = resume
    after = "it is tried again" if wait.reason == "auth" else "it resets"
    task.error = (
        f"{OPENALEX_WAIT_PREFIX}{wait.waiting_note}; "
        f"this professor is researched after {after} (about {resume:%H:%M} UTC)."
    )
    await notify_tasks(session, run_id)
    await session.commit()


async def _process_claimed(session, task: run_models.ResearchTask) -> bool:
    # After a rollback, expired attributes would lazy-load outside the async context.
    task_id, attempt, run_id = task.id, task.attempt, task.run_id
    run = await session.get(run_models.Run, task.run_id)
    handler = TASK_HANDLERS.get(task.task_type)
    label = f"{task.task_type} {task.id[:8]}"

    if run is None or run.user_id != task.user_id:
        # Ownership invariant: never execute cross-account.
        task.status = run_models.TaskStatus.error
        task.error = "Task owner does not match its run; refusing to execute"
        task.finished_at = utcnow_naive()
        await session.commit()
        return True

    if handler is None:
        if await _mid_run_mark(session, task, label):
            await note_tasks_drained(session, task.run_id)
            await session.commit()
            return True
        task.status = run_models.TaskStatus.error
        task.error = f"No handler for task_type={task.task_type}"
        task.finished_at = utcnow_naive()

        await session.commit()
        await note_tasks_drained(session, task.run_id)
        await session.commit()
        return True

    print(f"[worker] claimed {label} (run {task.run_id[:8]})", flush=True)

    async def on_checkpoint(messages: list[dict]) -> None:
        task.messages_json = json.dumps(messages, default=str)
        task.updated_at = utcnow_naive()
        await session.commit()

    resume_messages = None
    checkpoint = task.messages_json
    if checkpoint:
        try:
            resume_messages = json.loads(checkpoint)
            print(f"[worker] resuming {label} from checkpoint", flush=True)
        except (json.JSONDecodeError, TypeError):
            resume_messages = None
    # Counted per model call, so a failed or halted task still records its spend.
    spent = {"input_tokens": 0, "output_tokens": 0}
    task_usage.set(spent)
    try:
        result = await handler(
            session,
            task,
            run,
            on_event=_make_event_sink(session, task, label),
            resume_messages=resume_messages,
            on_checkpoint=on_checkpoint,
        )
        if await _mid_run_mark(session, task, label):
            _charge(task, spent)
            await note_tasks_drained(session, task.run_id)
            await session.commit()
            return True
        task.status = run_models.TaskStatus.done
        task.error = None
        task.final_text = result.get("final_text")
        task.finished_at = utcnow_naive()
        _charge(task, result.get("usage") or {})
        _record_metrics(task, spent)
        task.turns = result.get("turns")
        task.messages_json = None
        if task.task_type == "draft_email":
            from api.notifications import events as notification_events

            run_row = await session.get(run_models.Run, run_id)
            if run_row is not None:
                await notification_events.drafts_ready(session, run_row, task_id, attempt)
        nudges = result.get("nudges", 0)
        nudge_note = f" ({nudges} empty-finish nudges)" if nudges else ""
        if spent.get("cache_read_tokens"):
            nudge_note += (
                f", {spent['cache_read_tokens']} of {spent['input_tokens']} "
                "input tokens from the prompt cache"
            )
        print(
            f"[worker] done {label} in {task.turns} turns{nudge_note}: "
            f"{_preview(task.final_text or '', 80)}",
            flush=True,
        )
    except Exception as exc:  # noqa: BLE001 - log and move on, don't crash the worker
        # Roll back first: a poisoned Postgres transaction would raise InFailedSqlTransaction on commit.
        await session.rollback()
        if isinstance(exc, StaleDataError) or await _superseded(
            session, task_id, attempt
        ):
            print(f"[worker] {label} attempt {attempt} superseded", flush=True)
            return True
        # Expired by the rollback: reload before adding this attempt's spend.
        await session.refresh(task, attribute_names=["input_tokens", "output_tokens"])
        if await _mid_run_mark(session, task, label):
            _charge(task, spent)
            # run_id, not task.run_id: the rollback expired the row.
            await note_tasks_drained(session, run_id)
            await session.commit()
            return True
        _charge(task, spent)
        if isinstance(exc, ModelAllowanceRefused):
            await _park_for_allowance(session, task, run_id, exc.message)
            print(f"[worker] PAUSED {label}: {exc.message}", flush=True)
            return True
        if isinstance(exc, TaskHalted):
            await _honor_halt(session, task, run_id, exc.reason)
            print(f"[worker] HALTED {label}: {exc.reason}", flush=True)
            return True
        if isinstance(exc, OpenAlexWait):
            await _wait_for_openalex(session, task, run_id, exc)
            print(f"[worker] WAITING {label}: OpenAlex {exc.reason} until {exc.until:%H:%M} UTC", flush=True)
            return True
        # Expired by the rollback too.
        await session.refresh(task, attribute_names=["task_type", "target_name"])
        if task.task_type == "discover_programs":
            # Discovery with its school budget full has done its job.
            from api.prospects.tools import discovery_complete

            await session.refresh(run)
            done = await discovery_complete(session, run, task.target_name)
            if done:
                task.status = run_models.TaskStatus.done
                task.error = None
                task.final_text = done
                task.finished_at = utcnow_naive()
                print(f"[worker] done {label} (budget reached; ignored: {exc})", flush=True)
                await session.commit()
                await note_tasks_drained(session, task.run_id)
                await session.commit()
                return True
        if is_transient(exc) and attempt < settings.max_task_attempts:
            # A slow or flaky model backend, not a broken task: requeue it.
            task.status = run_models.TaskStatus.pending
            task.started_at = None
            task.claimed_by = None
            task.error = (
                f"Retrying after {public_error(exc)} "
                f"(attempt {attempt} of {settings.max_task_attempts})"
            )
            print(f"[worker] REQUEUE {label} after: {type(exc).__name__}: {exc}", flush=True)
            await notify_tasks(session, run_id)
            await notify_work(session, run_id)
            await session.commit()
            return True
        task.status = run_models.TaskStatus.error
        # Shown to the user, so upstream bodies stay in the worker log.
        task.error = public_error(exc)
        task.finished_at = utcnow_naive()
        print(f"[worker] ERROR {label}: {type(exc).__name__}: {exc}", flush=True)
        from api.notifications import events as notification_events

        # Expired by the rollback: get() reloads it (None if deleted).
        run_row = await session.get(run_models.Run, run_id)
        if run_row is not None:
            await notification_events.run_attention(session, run_row, task.task_type)
    await session.commit()
    await note_tasks_drained(session, run_id)
    await session.commit()
    return True


class WorkSignal:
    """Wakes every idle claim loop; SKIP LOCKED makes the stampede safe."""

    def __init__(self) -> None:
        self._events: list[asyncio.Event] = []

    def register(self) -> asyncio.Event:
        event = asyncio.Event()
        self._events.append(event)
        return event

    def wake_all(self) -> None:
        for event in self._events:
            event.set()

    async def wait(self, event: asyncio.Event, timeout: float) -> None:
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except TimeoutError:
            pass
        event.clear()


async def _enqueue_listener(
    signal: WorkSignal, notifications: asyncio.Event | None = None
):
    """LISTEN and wake the claim and delivery loops; best-effort, polling is the backstop."""
    while True:
        conn = None
        try:
            conn = await asyncpg.connect(listener_dsn())

            def _on_notify(_conn, _pid, _channel, payload: str) -> None:
                parsed = parse_payload(payload)
                # Not "tasks": it fires on every progress write, waking loops for nothing.
                if parsed is not None and parsed[1] == "work":
                    signal.wake_all()
                elif (
                    parsed is not None
                    and parsed[1] == "notifications"
                    and notifications is not None
                ):
                    notifications.set()

            await conn.add_listener(CHANNEL, _on_notify)
            print("[worker] listening for enqueue notifications", flush=True)
            # Poll liveness: a silently dropped LISTEN would otherwise go unnoticed.
            while not conn.is_closed():
                await asyncio.sleep(30.0)
            raise ConnectionError("LISTEN connection closed")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - degrade to polling, then retry
            print(f"[worker] enqueue listener: {exc}; polling instead", flush=True)
            await asyncio.sleep(5.0)
        finally:
            if conn is not None:
                try:
                    await conn.close()
                except Exception:  # noqa: BLE001, S110 - best-effort close on teardown
                    pass


async def worker_loop(
    worker_id: int,
    poll_interval_seconds: float = 2.0,
    signal: WorkSignal | None = None,
):
    event = signal.register() if signal is not None else None
    while True:
        try:
            did_work = await process_one()
        except Exception as exc:  # noqa: BLE001 - one bad iteration must not kill every loop
            print(f"[worker] loop {worker_id} error: {exc!r}", flush=True)
            traceback.print_exc()
            did_work = False
        if not did_work:
            if signal is not None and event is not None:
                await signal.wait(event, poll_interval_seconds)
            else:
                await asyncio.sleep(poll_interval_seconds)


async def main_loop(concurrency: int = 1, poll_interval_seconds: float = 2.0):
    """Run worker loops concurrently; idle loops wait on enqueue notifies, polling as backstop."""
    concurrency = max(concurrency, 1)
    signal = WorkSignal()
    notifications_due = asyncio.Event()
    print(
        f"Worker started, polling research_tasks... (concurrency={concurrency})",
        flush=True,
    )

    daily_checked_at: float | None = None

    async def reaper_loop():
        nonlocal daily_checked_at
        while True:
            try:
                async with SessionLocal() as session:
                    requeued = await reap_stale_tasks(session)
                    if requeued:
                        print(f"[worker] requeued {requeued} stale task(s)", flush=True)
                    await prune_heartbeats(session)
                    from api.runs.retention import prune_traces

                    await prune_traces(session)
                    from api.account.export import sweep_expired_exports

                    await sweep_expired_exports(session)
                    from api.prospects.openalex import prune_stored_responses

                    await prune_stored_responses(session)
                    loop_now = asyncio.get_running_loop().time()
                    if daily_checked_at is None or loop_now - daily_checked_at >= 3600:
                        from api.notifications.deadlines import (
                            check_deadlines,
                            send_digests,
                        )

                        daily_checked_at = loop_now
                        reminders = await check_deadlines(session)
                        if reminders:
                            print(f"[worker] {reminders} deadline reminder(s)", flush=True)
                        await send_digests(session)
            except Exception as exc:  # noqa: BLE001 - housekeeping must not kill the loops
                print(f"[worker] reaper error: {exc!r}", flush=True)
                traceback.print_exc()
            await asyncio.sleep(60.0)

    async def delivery_loop():
        """Push and email notifications; the interval also releases rows held by quiet hours."""
        from api.notifications.delivery import deliver_pending

        while True:
            try:
                async with SessionLocal() as session:
                    await deliver_pending(session)
            except Exception as exc:  # noqa: BLE001 - delivery must not kill the loops
                print(f"[worker] notification delivery error: {exc!r}", flush=True)
                traceback.print_exc()
            try:
                await asyncio.wait_for(
                    notifications_due.wait(),
                    timeout=max(settings.notification_deliver_seconds, 1.0),
                )
            except TimeoutError:
                pass
            notifications_due.clear()

    async def heartbeat_loop():
        interval = max(settings.worker_heartbeat_seconds, 1)
        while True:
            try:
                async with SessionLocal() as session:
                    await heartbeat(session, WORKER_ID, concurrency)
            except Exception as exc:  # noqa: BLE001 - liveness writes must not kill the loops
                print(f"[worker] heartbeat error: {exc!r}", flush=True)
                traceback.print_exc()
            await asyncio.sleep(interval)

    try:
        await asyncio.gather(
            *(worker_loop(i, poll_interval_seconds, signal) for i in range(concurrency)),
            _enqueue_listener(signal, notifications_due),
            reaper_loop(),
            heartbeat_loop(),
            delivery_loop(),
        )
    finally:
        await retire_heartbeat()
