"""The worker: claim scan tasks, run their agents, conclude them; plus housekeeping loops.

Claims use FOR UPDATE SKIP LOCKED, so workers scale horizontally. A claim is a lease
(claimed_by) fenced by `attempt`: a task whose worker dies is requeued by the reaper,
and the stale attempt's writes fail. Tasks checkpoint every turn and resume from there.
"""

import asyncio
import contextvars
import json
import os
import socket
import traceback
import uuid
from datetime import timedelta

import asyncpg
from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.orm.exc import StaleDataError

from api.agent.llm.base import is_transient
from api.agent.orchestrator import TaskHalted, task_usage
from api.core.config import settings
from api.core.db import SessionLocal, listener_dsn
from api.core.egress import public_error
from api.core.time import utcnow_naive
from api.opportunities.tasks import run_discover_opportunities
from api.scans import models as m
from api.scans.notify import CHANNEL, notify_work, parse_payload
from api.scans.service import note_tasks_drained

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
HEARTBEAT_TTL = timedelta(days=1)

TASK_HANDLERS = {
    "discover_opportunities": run_discover_opportunities,
}

#: (task_id, attempt) this coroutine runs, so dispatch can refuse work once it is halted.
current_lease: contextvars.ContextVar[tuple[str, int] | None] = contextvars.ContextVar(
    "current_lease", default=None
)


def heartbeat_stale_after() -> timedelta:
    return timedelta(seconds=max(settings.worker_heartbeat_seconds, 1) * 4)


def _live_worker_ids():
    return select(m.WorkerHeartbeat.worker_id).where(
        m.WorkerHeartbeat.last_seen_at >= utcnow_naive() - heartbeat_stale_after()
    )


async def current_lease_halt(session) -> str | None:
    """Why the running attempt must stop, or None; read fresh every tool batch."""
    lease = current_lease.get()
    if lease is None:
        return None
    task_id, attempt = lease
    row = (
        await session.execute(
            select(m.ScanTask.status, m.ScanTask.attempt).where(m.ScanTask.id == task_id)
        )
    ).one_or_none()
    if row is None:
        return "deleted"
    if row.attempt != attempt:
        return "superseded"
    status = m.status_str(row.status)
    return None if status == m.TaskStatus.running.value else status


async def heartbeat(session, worker_id: str = WORKER_ID, concurrency: int = 1) -> None:
    now = utcnow_naive()
    row = await session.get(m.WorkerHeartbeat, worker_id)
    if row is None:
        session.add(m.WorkerHeartbeat(worker_id=worker_id, concurrency=concurrency, started_at=now, last_seen_at=now))
    else:
        row.concurrency = concurrency
        row.last_seen_at = now
    await session.commit()


async def prune_heartbeats(session) -> None:
    await session.execute(
        delete(m.WorkerHeartbeat).where(m.WorkerHeartbeat.last_seen_at < utcnow_naive() - HEARTBEAT_TTL)
    )
    await session.commit()


async def claim_next_task(session, scan_id: str | None = None) -> m.ScanTask | None:
    """Claim the oldest pending task of a running scan (scan_id is a test seam)."""
    query = (
        select(m.ScanTask)
        .join(m.Scan, m.ScanTask.scan_id == m.Scan.id)
        .where(
            m.ScanTask.status == m.TaskStatus.pending,
            m.Scan.status == "running",
            # Not while an earlier attempt is still live; it releases the lease when it ends.
            or_(m.ScanTask.claimed_by.is_(None), m.ScanTask.claimed_by.not_in(_live_worker_ids())),
        )
        .order_by(m.ScanTask.created_at)
        .limit(1)
        .with_for_update(skip_locked=True, of=m.ScanTask)
    )
    if scan_id is not None:
        query = query.where(m.ScanTask.scan_id == scan_id)
    task = (await session.execute(query)).scalar_one_or_none()
    if task is not None:
        task.status = m.TaskStatus.running
        task.started_at = utcnow_naive()
        task.claimed_by = WORKER_ID
        task.attempt = (task.attempt or 0) + 1
        await session.commit()
    return task


async def reap_stale_tasks(session) -> int:
    """Requeue running tasks whose worker's heartbeat is stale or gone."""
    cutoff = utcnow_naive() - timedelta(minutes=settings.stale_task_minutes)
    rows = (
        await session.execute(
            select(m.ScanTask).where(
                m.ScanTask.status == m.TaskStatus.running,
                or_(
                    and_(m.ScanTask.claimed_by.is_(None), m.ScanTask.updated_at < cutoff),
                    and_(
                        m.ScanTask.claimed_by.is_not(None),
                        m.ScanTask.claimed_by.not_in(_live_worker_ids()),
                    ),
                ),
            )
        )
    ).scalars().all()
    for row in rows:
        row.status = m.TaskStatus.pending
        row.started_at = None
        row.claimed_by = None
    for scan_id in {r.scan_id for r in rows}:
        await notify_work(session, scan_id)
    await session.commit()
    return len(rows)


def _preview(value: object, limit: int = 100) -> str:
    if isinstance(value, dict) and value:
        value = next(iter(value.values()))
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "..."


def _event_sink(session, task: m.ScanTask, label: str):
    """Persist the growing trace on the task row (previews only), for the live view."""
    events: list[dict] = []
    if task.log:
        try:
            loaded = json.loads(task.log)
            events = loaded if isinstance(loaded, list) else []
        except (json.JSONDecodeError, TypeError):
            events = []

    async def on_event(event: dict) -> None:
        entry = {k: v for k, v in event.items() if k != "result"}
        entry["at"] = utcnow_naive().isoformat() + "Z"
        events.append(entry)
        if entry.get("kind") == "turn":
            print(f"[worker] [{label} turn {entry['turn']}] {_preview(entry.get('note') or '')}", flush=True)
        else:
            status = "ok" if entry.get("ok") else "ERROR"
            print(
                f"[worker] [{label} turn {entry['turn']}] {entry['tool']}({_preview(entry['input'])}) -> {status}",
                flush=True,
            )
        task.log = json.dumps(events)
        await session.commit()

    return on_event


def _charge(task: m.ScanTask, usage: dict) -> None:
    task.input_tokens = (task.input_tokens or 0) + usage.get("input_tokens", 0)
    task.output_tokens = (task.output_tokens or 0) + usage.get("output_tokens", 0)
    if usage.get("turns"):
        task.turns = usage["turns"]


async def _superseded(session, task_id: str, attempt: int) -> bool:
    current = (
        await session.execute(select(m.ScanTask.attempt).where(m.ScanTask.id == task_id))
    ).scalar_one_or_none()
    return current != attempt


async def process_claimed(session, task: m.ScanTask) -> None:
    # After a rollback, expired attributes would lazy-load outside the async context.
    task_id, attempt, scan_id = task.id, task.attempt, task.scan_id
    scan = await session.get(m.Scan, scan_id)
    label = f"{task.task_type} {task_id[:8]}"
    handler = TASK_HANDLERS.get(task.task_type)
    if scan is None or scan.user_id != task.user_id or handler is None:
        task.status = m.TaskStatus.error
        task.error = "No handler for this task" if handler is None else "Task does not match its scan"
        task.finished_at = utcnow_naive()
        await note_tasks_drained(session, scan_id)
        await session.commit()
        return

    print(f"[worker] claimed {label} (scan {scan_id[:8]})", flush=True)

    async def on_checkpoint(messages: list[dict]) -> None:
        task.messages_json = json.dumps(messages, default=str)
        await session.commit()

    resume = None
    if task.messages_json:
        try:
            resume = json.loads(task.messages_json)
        except (json.JSONDecodeError, TypeError):
            resume = None
    spent = {"input_tokens": 0, "output_tokens": 0}
    task_usage.set(spent)
    try:
        result = await handler(
            session,
            task,
            scan,
            on_event=_event_sink(session, task, label),
            resume_messages=resume,
            on_checkpoint=on_checkpoint,
        )
        task.status = m.TaskStatus.done
        task.error = None
        task.final_text = result.get("final_text")
        task.finished_at = utcnow_naive()
        task.messages_json = None
        _charge(task, spent)
        task.turns = result.get("turns")
        print(f"[worker] done {label} in {task.turns} turns: {_preview(task.final_text or '', 80)}", flush=True)
    except Exception as exc:  # noqa: BLE001 - log and move on, never crash the worker
        # Roll back first: a poisoned transaction would fail the commit below.
        await session.rollback()
        if isinstance(exc, StaleDataError) or await _superseded(session, task_id, attempt):
            print(f"[worker] {label} attempt {attempt} superseded", flush=True)
            return
        task = await session.get(m.ScanTask, task_id)
        if task is None:
            return
        _charge(task, spent)
        if isinstance(exc, TaskHalted):
            task.status = m.TaskStatus.cancelled
            task.finished_at = utcnow_naive()
            print(f"[worker] HALTED {label}: {exc.reason}", flush=True)
        elif is_transient(exc) and attempt < settings.max_task_attempts:
            # A slow or flaky model backend, not a broken task: requeue it.
            task.status = m.TaskStatus.pending
            task.started_at = None
            task.claimed_by = None
            task.error = f"Retrying after {public_error(exc)} (attempt {attempt} of {settings.max_task_attempts})"
            print(f"[worker] REQUEUE {label}: {type(exc).__name__}: {exc}", flush=True)
            await notify_work(session, scan_id)
            await session.commit()
            return
        else:
            task.status = m.TaskStatus.error
            task.error = public_error(exc)
            task.finished_at = utcnow_naive()
            print(f"[worker] ERROR {label}: {type(exc).__name__}: {exc}", flush=True)
            scan = await session.get(m.Scan, scan_id)
            if scan is not None:
                from api.notifications import events

                await events.scan_attention(session, scan)
    await session.commit()
    await note_tasks_drained(session, scan_id)
    await session.commit()


async def _release_lease(task_id: str, attempt: int) -> None:
    """Drop this attempt's claim (fenced); the reaper frees it if this fails."""
    try:
        async with SessionLocal() as session:
            await session.execute(
                update(m.ScanTask)
                .where(m.ScanTask.id == task_id, m.ScanTask.attempt == attempt)
                .values(claimed_by=None)
                .execution_options(synchronize_session=False)
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        print(f"[worker] lease release failed for {task_id[:8]}: {exc}", flush=True)


async def process_one() -> bool:
    async with SessionLocal() as session:
        task = await claim_next_task(session)
        if task is None:
            return False
        task_id, attempt = task.id, task.attempt
        token = current_lease.set((task_id, attempt))
        try:
            await process_claimed(session, task)
        except StaleDataError:
            await session.rollback()
        finally:
            current_lease.reset(token)
            await _release_lease(task_id, attempt)
        return True


async def _listen(work: asyncio.Event, notifications: asyncio.Event) -> None:
    """LISTEN and wake the claim and delivery loops; polling is the backstop."""
    while True:
        conn = None
        try:
            conn = await asyncpg.connect(listener_dsn())

            def on_notify(_conn, _pid, _channel, payload: str) -> None:
                parsed = parse_payload(payload)
                if parsed is None:
                    return
                (work if parsed[1] == "work" else notifications).set()

            await conn.add_listener(CHANNEL, on_notify)
            while not conn.is_closed():
                await asyncio.sleep(30.0)
            raise ConnectionError("LISTEN connection closed")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - degrade to polling, then retry
            print(f"[worker] listener: {exc}; polling instead", flush=True)
            await asyncio.sleep(5.0)
        finally:
            if conn is not None:
                try:
                    await conn.close()
                except Exception:  # noqa: BLE001, S110
                    pass


async def _wait(event: asyncio.Event, timeout: float) -> None:
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
    except TimeoutError:
        pass
    event.clear()


async def hourly_jobs(session) -> None:
    """Deadline reminders, email digests, trace pruning and the scheduled sweep."""
    from api.notifications.deadlines import check_deadlines, send_digests
    from api.opportunities.sweep import maybe_sweep
    from api.scans.service import prune_traces

    reminders = await check_deadlines(session)
    if reminders:
        print(f"[worker] {reminders} deadline reminder(s)", flush=True)
    await send_digests(session)
    await prune_traces(session)
    if sweep := await maybe_sweep(session):
        print(f"[worker] started opportunity sweep {sweep[:8]}", flush=True)


async def main_loop(concurrency: int = 1, poll_seconds: float = 2.0) -> None:
    concurrency = max(concurrency, 1)
    work = asyncio.Event()
    notifications_due = asyncio.Event()
    print(f"Worker started (concurrency={concurrency})", flush=True)

    async def worker(index: int) -> None:
        while True:
            try:
                did = await process_one()
            except Exception as exc:  # noqa: BLE001
                print(f"[worker] loop {index} error: {exc!r}", flush=True)
                traceback.print_exc()
                did = False
            if not did:
                await _wait(work, poll_seconds)

    async def housekeeping() -> None:
        last_hourly: float | None = None
        while True:
            try:
                async with SessionLocal() as session:
                    if requeued := await reap_stale_tasks(session):
                        print(f"[worker] requeued {requeued} stale task(s)", flush=True)
                    await heartbeat(session, WORKER_ID, concurrency)
                    await prune_heartbeats(session)
                    now = asyncio.get_running_loop().time()
                    if last_hourly is None or now - last_hourly >= 3600:
                        last_hourly = now
                        await hourly_jobs(session)
            except Exception as exc:  # noqa: BLE001 - housekeeping must not kill the loops
                print(f"[worker] housekeeping error: {exc!r}", flush=True)
                traceback.print_exc()
            await asyncio.sleep(max(settings.worker_heartbeat_seconds, 1))

    async def delivery() -> None:
        from api.notifications.delivery import deliver_pending

        while True:
            try:
                async with SessionLocal() as session:
                    await deliver_pending(session)
            except Exception as exc:  # noqa: BLE001
                print(f"[worker] notification delivery error: {exc!r}", flush=True)
            await _wait(notifications_due, max(settings.notification_deliver_seconds, 1.0))

    try:
        await asyncio.gather(
            *(worker(i) for i in range(concurrency)),
            _listen(work, notifications_due),
            housekeeping(),
            delivery(),
        )
    finally:
        try:
            async with SessionLocal() as session:
                await session.execute(delete(m.WorkerHeartbeat).where(m.WorkerHeartbeat.worker_id == WORKER_ID))
                await session.commit()
        except Exception:  # noqa: BLE001, S110 - staleness covers it
            pass
