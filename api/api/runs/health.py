"""Operational health: database, work queue, and worker liveness (from heartbeat rows)."""

import time
from datetime import timedelta

from sqlalchemy import func, select, text

from api.candidates.models import CandidateScore
from api.core.config import settings
from api.core.db import SessionLocal, engine
from api.core.time import utcnow_naive
from api.outreach.models import EmailDraft
from api.runs.models import ResearchTask, Run, TaskStatus, WorkerHeartbeat, status_str

_utcnow = utcnow_naive


async def check_database(user_id: str | None = None) -> dict:
    """Reachability and latency; row counts only when scoped to a user_id."""
    started = time.perf_counter()
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
            run_filter = [Run.user_id == user_id] if user_id is not None else []
            task_filter = [ResearchTask.user_id == user_id] if user_id is not None else []
            candidate_filter = [CandidateScore.user_id == user_id] if user_id is not None else []
            draft_filter = [EmailDraft.user_id == user_id] if user_id is not None else []
            runs = (
                await session.execute(
                    select(func.count()).select_from(Run).where(*run_filter)
                )
            ).scalar() or 0
            tasks = (
                await session.execute(
                    select(func.count()).select_from(ResearchTask).where(*task_filter)
                )
            ).scalar() or 0
            candidates = (
                await session.execute(
                    select(func.count()).select_from(CandidateScore).where(*candidate_filter)
                )
            ).scalar() or 0
            drafts = (
                await session.execute(
                    select(func.count()).select_from(EmailDraft).where(*draft_filter)
                )
            ).scalar() or 0
    except Exception as exc:  # noqa: BLE001 - health must report, never raise
        return {"reachable": False, "error": str(exc)}
    return {
        "reachable": True,
        "dialect": engine.dialect.name,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "runs": runs,
        "tasks": tasks,
        "candidates": candidates,
        "drafts": drafts,
    }


async def check_queue(user_id: str) -> dict:
    """One account's work-queue state."""
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(ResearchTask.status, func.count())
                .where(ResearchTask.user_id == user_id)
                .group_by(ResearchTask.status)
            )
        ).all()
        depth = {"pending": 0, "running": 0, "done": 0, "error": 0}
        for status, count in rows:
            key = status_str(status)
            depth[key] = depth.get(key, 0) + count

        cutoff = utcnow_naive() - timedelta(minutes=settings.stale_task_minutes)
        stale = (
            await session.execute(
                select(func.count())
                .select_from(ResearchTask)
                .where(
                    ResearchTask.user_id == user_id,
                    ResearchTask.status == TaskStatus.running,
                    func.coalesce(ResearchTask.updated_at, ResearchTask.created_at)
                    < cutoff,
                )
            )
        ).scalar() or 0

        last_activity = (
            await session.execute(
                select(
                    func.max(
                        func.coalesce(ResearchTask.updated_at, ResearchTask.created_at)
                    )
                ).where(ResearchTask.user_id == user_id)
            )
        ).scalar()

        # `error` is lifetime; `degraded` keys off this windowed count so old failures don't pin it.
        error_cutoff = utcnow_naive() - timedelta(
            minutes=settings.health_error_window_minutes
        )
        recent_errors = (
            await session.execute(
                select(func.count())
                .select_from(ResearchTask)
                .where(
                    ResearchTask.user_id == user_id,
                    ResearchTask.status == TaskStatus.error,
                    func.coalesce(ResearchTask.updated_at, ResearchTask.created_at)
                    >= error_cutoff,
                )
            )
        ).scalar() or 0

        # Pending but not claimable until the OpenAlex budget resets.
        waiting = (
            await session.execute(
                select(func.count())
                .select_from(ResearchTask)
                .where(
                    ResearchTask.user_id == user_id,
                    ResearchTask.status == TaskStatus.pending,
                    ResearchTask.wait_until > utcnow_naive(),
                )
            )
        ).scalar() or 0

        eta = await _queue_eta(session, user_id, depth["pending"] - waiting + depth["running"], depth["running"])

    return {
        **depth,
        "eta_seconds": eta,
        "waiting_for_openalex": waiting,
        "stale_running": stale,
        "recent_error": recent_errors,
        "error_window_minutes": settings.health_error_window_minutes,
        "last_activity_at": last_activity.isoformat() if last_activity else None,
    }


ETA_WINDOW = timedelta(minutes=15)
ETA_MIN_FINISHED = 3
ETA_SAMPLE = 20


async def _queue_eta(session, user_id: str, remaining: int, running: int) -> int | None:
    """Seconds to clear open tasks at the recent finish rate, else the average task length."""
    if remaining <= 0:
        return None
    now = utcnow_naive()
    finished = ResearchTask.status.in_([TaskStatus.done, TaskStatus.error])
    recent = (
        await session.execute(
            select(func.count(), func.min(ResearchTask.started_at)).where(
                ResearchTask.user_id == user_id,
                finished,
                ResearchTask.finished_at >= now - ETA_WINDOW,
            )
        )
    ).one()
    if recent[0] >= ETA_MIN_FINISHED and recent[1] is not None:
        span = (now - max(recent[1], now - ETA_WINDOW)).total_seconds()
        return round(remaining * max(span, 60) / recent[0])
    durations = (
        await session.execute(
            select(ResearchTask.finished_at - ResearchTask.started_at)
            .where(ResearchTask.user_id == user_id, finished, ResearchTask.started_at.is_not(None), ResearchTask.finished_at.is_not(None))
            .order_by(ResearchTask.finished_at.desc())
            .limit(ETA_SAMPLE)
        )
    ).scalars().all()
    if not durations:
        return None
    average = sum(d.total_seconds() for d in durations) / len(durations)
    return round(average * remaining / max(running, 1))


async def check_workers() -> dict:
    """Workers from heartbeats; one with no recent beat is reported stale, not hidden."""
    threshold = max(settings.worker_heartbeat_seconds, 1) * 4
    now = utcnow_naive()
    workers = []
    async with SessionLocal() as session:
        rows = (
            (
                await session.execute(
                    select(WorkerHeartbeat).order_by(
                        WorkerHeartbeat.last_seen_at.desc()
                    )
                )
            )
            .scalars()
            .all()
        )
        # Materialize inside the session to avoid DetachedInstanceError.
        for row in rows:
            lag = (now - row.last_seen_at).total_seconds() if row.last_seen_at else None
            workers.append(
                {
                    "worker_id": row.worker_id,
                    "concurrency": row.concurrency,
                    "started_at": row.started_at.isoformat()
                    if row.started_at
                    else None,
                    "last_seen_at": row.last_seen_at.isoformat()
                    if row.last_seen_at
                    else None,
                    "lag_seconds": lag,
                    "alive": lag is not None and lag <= threshold,
                }
            )
    return {
        "alive": sum(1 for w in workers if w["alive"]),
        "stale": sum(1 for w in workers if not w["alive"]),
        "workers": workers,
    }


async def get_health(user_id: str) -> dict:
    """One account's health summary; worker liveness is global (processes are shared)."""
    database = await check_database(user_id)
    queue = await check_queue(user_id) if database.get("reachable") else {}
    workers = await check_workers() if database.get("reachable") else {}
    # Otherwise runs would sit at "researching..." forever with no worker alive.
    no_workers = bool(database.get("reachable")) and (
        workers.get("alive", 0) == 0
        and queue.get("pending", 0) + queue.get("running", 0) > 0
    )
    degraded = (
        not database.get("reachable")
        or queue.get("stale_running", 0) > 0
        or queue.get("recent_error", 0) > 0
        or no_workers
    )
    return {
        "status": "degraded" if degraded else "ok",
        "no_workers": no_workers,
        "database": database,
        "queue": queue,
        "workers": workers,
    }
