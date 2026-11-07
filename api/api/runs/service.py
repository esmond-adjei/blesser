"""Run service: runs, progress, lifecycle, usage, the SSE feed, deletion."""

import asyncio
import json
from datetime import datetime
from typing import Any, cast

import asyncpg
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.candidates import models as candidate_models
from api.candidates import scoring
from api.core.config import settings
from api.core.db import SessionLocal, listener_dsn
from api.core.exceptions import BadRequestError, NotFoundError
from api.core.time import duration_seconds, utcnow_naive
from api.cv import models as cv_models
from api.outreach import models as outreach_models
from api.prospects import tiers
from api.runs import models as run_models
from api.runs.agents import agent_states
from api.runs.budgets import default_run_budgets
from api.runs.lifecycle import note_work_enqueued
from api.runs.notify import CHANNEL, notify_tasks, notify_work, parse_payload


async def cache_interest_embedding(run: run_models.Run) -> None:
    """Best-effort; runs in a thread so sync SDK clients don't block the event loop."""
    from api.billing import service as billing

    # Operator-key spend: skip once the account has used today's tool-call budget.
    if (
        await billing.tool_call_refusal(
            run.user_id,
            "scoring",
            settings.embedding_provider,
            settings.embedding_model,
        )
        is not None
    ):
        return
    try:
        vecs = await asyncio.to_thread(scoring.embed_texts, [run.interest_statement])
    except Exception:  # noqa: BLE001 - cache is an optimization, never fatal
        vecs = None
    if vecs:
        run.interest_embedding = json.dumps(vecs[0])


async def get_run_or_404(
    session: AsyncSession, run_id: str, user_id: str
) -> run_models.Run:
    """Cross-account ids read as missing: ownership is never distinguished from absence."""
    run = (
        (
            await session.execute(
                select(run_models.Run).where(
                    run_models.Run.id == run_id,
                    run_models.Run.user_id == user_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if not run:
        raise NotFoundError("Run not found")
    return run


def _empty_task_counts() -> dict[str, int]:
    return {"pending": 0, "running": 0, "done": 0, "error": 0}


async def run_progress(
    session: AsyncSession, run_id: str
) -> tuple[dict[str, int], int]:
    task_rows = (
        await session.execute(
            select(run_models.ResearchTask.status, func.count())
            .where(run_models.ResearchTask.run_id == run_id)
            .group_by(run_models.ResearchTask.status)
        )
    ).all()
    tasks = _empty_task_counts()
    for status, count in task_rows:
        key = run_models.status_str(status)
        tasks[key] = tasks.get(key, 0) + count
    candidates = (
        await session.execute(
            select(func.count())
            .select_from(candidate_models.CandidateScore)
            .where(candidate_models.CandidateScore.run_id == run_id)
        )
    ).scalar() or 0
    return tasks, candidates


async def all_run_progress(
    session: AsyncSession, user_id: str
) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    """Task and candidate counts for all of an account's runs in two grouped queries (polled by every tab)."""
    tasks: dict[str, dict[str, int]] = {}
    task_rows = (
        await session.execute(
            select(
                run_models.ResearchTask.run_id,
                run_models.ResearchTask.status,
                func.count(),
            )
            .where(run_models.ResearchTask.user_id == user_id)
            .group_by(run_models.ResearchTask.run_id, run_models.ResearchTask.status)
        )
    ).all()
    for run_id, status, count in task_rows:
        bucket = tasks.setdefault(run_id, _empty_task_counts())
        key = run_models.status_str(status)
        bucket[key] = bucket.get(key, 0) + count
    candidate_rows = (
        await session.execute(
            select(candidate_models.CandidateScore.run_id, func.count())
            .where(candidate_models.CandidateScore.user_id == user_id)
            .group_by(candidate_models.CandidateScore.run_id)
        )
    ).all()
    return tasks, {run_id: count for run_id, count in candidate_rows}


FINISHED_RUN_STATUSES = ("done", "cancelled")


def run_out_dict(
    run: run_models.Run,
    tasks: dict,
    candidates: int,
    finished_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> dict:
    return {
        "id": run.id,
        "region": run.region,
        "field": run.field,
        "degree_level": run.degree_level,
        "status": run.status,
        "interest_statement": run.interest_statement,
        "created_at": run.created_at,
        "finished_at": finished_at,
        "elapsed_seconds": duration_seconds(run.created_at, finished_at or utcnow_naive()),
        "updated_at": updated_at,
        "max_programs": run.max_programs,
        "max_professors": run.max_professors,
        "max_professors_per_program": run.max_professors_per_program,
        "tasks": tasks,
        "candidates": candidates,
        "flow_id": run.flow_id,
        "school_tiers": tiers.load(run),
        "llm_provider": run.llm_provider,
        "agent_states": agent_states(run),
    }


async def validate_interest_document(
    session: AsyncSession,
    user_id: str,
    document_id: str | None,
    interest_statement: str,
) -> str | None:
    """An owned interest document id, only when it matches the run text."""
    if document_id is None:
        return None
    document = (
        await session.execute(
            select(cv_models.CvDocument).where(
                cv_models.CvDocument.id == document_id,
                cv_models.CvDocument.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if document is None or document.kind != "interest":
        raise NotFoundError("Interest statement not found")
    if document.markdown.strip() != interest_statement.strip():
        raise BadRequestError("Interest statement text has changed; select it again")
    return document.id


async def create_run(
    session: AsyncSession,
    user_id: str,
    *,
    region: str,
    field: str,
    degree_level: str,
    interest_statement: str,
    interest_document_id: str | None = None,
    max_programs: int | None = None,
    max_professors: int | None = None,
    max_professors_per_program: int | None = None,
    initial_tasks: list[dict] | None = None,
    flow_id: str | None = None,
    school_tiers: list[str] | None = None,
    llm_provider: str | None = None,
) -> run_models.Run:
    """Create a run and queue `initial_tasks` (default: discovery). Commits."""
    max_programs, max_professors, max_professors_per_program = default_run_budgets(
        max_programs, max_professors, max_professors_per_program
    )
    interest_document_id = await validate_interest_document(
        session, user_id, interest_document_id, interest_statement
    )
    run = run_models.Run(
        user_id=user_id,
        region=region,
        field=field,
        degree_level=degree_level,
        interest_statement=interest_statement,
        interest_document_id=interest_document_id,
        status="running",
        max_programs=max_programs,
        max_professors=max_professors,
        max_professors_per_program=max_professors_per_program,
        flow_id=flow_id,
        school_tiers=tiers.dump(school_tiers),
        llm_provider=llm_provider,
    )
    session.add(run)
    await session.flush()

    await cache_interest_embedding(run)

    # Several tiers or regions: discovery runs as parallel shards.
    default_tasks = [
        {"task_type": "discover_programs", "target_name": shard}
        for shard in tiers.discovery_shards(run)
    ]
    for spec in initial_tasks if initial_tasks is not None else default_tasks:
        session.add(
            run_models.ResearchTask(run_id=run.id, user_id=user_id, **spec)
        )
    await notify_work(session, run.id)
    await session.commit()
    return run


async def run_finished_at(session: AsyncSession, run: run_models.Run) -> datetime | None:
    """A done or cancelled run's last task finish, else None."""
    if run_models.status_str(run.status) not in FINISHED_RUN_STATUSES:
        return None
    return (
        await session.execute(
            select(func.max(run_models.ResearchTask.finished_at)).where(
                run_models.ResearchTask.run_id == run.id
            )
        )
    ).scalar()


async def run_updated_at(session: AsyncSession, run: run_models.Run) -> datetime:
    latest = (
        await session.execute(
            select(func.max(run_models.ResearchTask.updated_at)).where(
                run_models.ResearchTask.run_id == run.id
            )
        )
    ).scalar()
    return max(latest, run.created_at) if latest else run.created_at


async def run_detail(session: AsyncSession, run: run_models.Run) -> dict:
    tasks, candidates = await run_progress(session, run.id)
    return run_out_dict(
        run,
        tasks,
        candidates,
        await run_finished_at(session, run),
        await run_updated_at(session, run),
    )


async def list_runs(
    session: AsyncSession,
    user_id: str,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    """Newest first; the id breaks created_at ties so pages never overlap."""
    stmt = (
        select(run_models.Run)
        .where(run_models.Run.user_id == user_id)
        .order_by(run_models.Run.created_at.desc(), run_models.Run.id.desc())
        .offset(offset)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    runs = result.scalars().all()
    tasks_by_run, candidates_by_run = await all_run_progress(session, user_id)
    return [
        run_out_dict(
            run,
            tasks_by_run.get(run.id, _empty_task_counts()),
            candidates_by_run.get(run.id, 0),
        )
        for run in runs
    ]


RUN_BUDGET_FIELDS = {"max_programs", "max_professors", "max_professors_per_program"}


async def update_run(
    session: AsyncSession, user_id: str, run_id: str, data: dict
) -> run_models.Run:
    """A new interest statement re-embeds the run cache."""
    run = await get_run_or_404(session, run_id, user_id)
    data = dict(data)
    if (
        "interest_statement" in data
        and data["interest_statement"] != run.interest_statement
    ):
        run.interest_statement = data.pop("interest_statement")
        run.interest_document_id = None
        run.interest_embedding = None
        await cache_interest_embedding(run)
    if "llm_provider" in data:
        # Checked by the route; applies from the next model call.
        run.llm_provider = data.pop("llm_provider")
    budgets_changed = False
    for key in RUN_BUDGET_FIELDS:
        if key in data and data[key] != getattr(run, key):
            setattr(run, key, data[key])
            budgets_changed = True
    if budgets_changed and run.status in ("running", "done"):
        # A raised cap can release waiting leads, reopening a finished run.
        from api.prospects.leads import release_deferred_leads

        was_done = run.status == "done"
        run.status = "running"
        if await release_deferred_leads(session, run_id):
            await note_work_enqueued(session, run_id)
        elif was_done:
            run.status = "done"
    await notify_tasks(session, run_id)
    await session.commit()
    return run


async def set_run_status(
    session: AsyncSession, user_id: str, run_id: str, status: str
) -> dict:
    run = await get_run_or_404(session, run_id, user_id)
    run.status = status
    if status in ("paused", "cancelled"):
        # The worker honors this mark at the next turn instead of concluding them.
        await session.execute(
            update(run_models.ResearchTask)
            .where(
                run_models.ResearchTask.run_id == run_id,
                run_models.ResearchTask.status == run_models.TaskStatus.running,
            )
            .values(status=run_models.TaskStatus.pending, started_at=None)
        )
    await notify_tasks(session, run_id)
    await session.commit()
    return {"status": status}


async def resume_run(session: AsyncSession, user_id: str, run_id: str) -> dict:
    run = await get_run_or_404(session, run_id, user_id)
    if run.status not in ("paused", "cancelled"):
        raise BadRequestError(f"Run is {run.status}; only paused/cancelled runs resume")
    run.status = "running"
    # Requeue tasks parked for allowance; tasks the person paused stay paused.
    from api.agent.orchestrator import ALLOWANCE_PAUSE_PREFIX

    await session.execute(
        update(run_models.ResearchTask)
        .where(
            run_models.ResearchTask.run_id == run_id,
            run_models.ResearchTask.status == run_models.TaskStatus.paused,
            run_models.ResearchTask.error.startswith(ALLOWANCE_PAUSE_PREFIX),
        )
        .values(status=run_models.TaskStatus.pending, error=None)
    )
    await notify_tasks(session, run_id)
    await notify_work(session, run_id)
    await session.commit()
    return {"status": "running"}


async def control_agent(
    session: AsyncSession, user_id: str, run_id: str, task_type: str, action: str
) -> dict:
    from api.prospects.leads import release_deferred_leads
    from api.runs import agents
    from api.runs.lifecycle import note_tasks_drained

    actions = {
        "pause": agents.pause_agent,
        "resume": agents.resume_agent,
        "cancel": agents.cancel_agent,
    }
    if action not in actions:
        raise BadRequestError(f"Unknown action {action!r}: pause, resume or cancel.")
    run = await get_run_or_404(session, run_id, user_id)
    out = await actions[action](session, run, task_type)
    if action == "resume":
        # Reopen a done run first: leads are only released while it runs.
        await note_work_enqueued(session, run_id)
        await release_deferred_leads(session, run_id)
    else:
        await note_tasks_drained(session, run_id)
    await session.commit()
    return {"agent": task_type, **out, "agent_states": agents.agent_states(run)}


async def retry_failed(session: AsyncSession, user_id: str, run_id: str) -> dict:
    await get_run_or_404(session, run_id, user_id)
    result = await session.execute(
        update(run_models.ResearchTask)
        .where(
            run_models.ResearchTask.run_id == run_id,
            run_models.ResearchTask.status == run_models.TaskStatus.error,
        )
        .values(status=run_models.TaskStatus.pending, error=None)
    )
    retried = cast(int, cast(Any, result).rowcount)
    if retried:
        await note_work_enqueued(session, run_id)
    await session.commit()
    return {"retried": retried}


def active_seconds(tasks, now: datetime) -> float:
    """Wall-clock time any task was working; idle gaps (e.g. a rerun days later) don't count."""
    spans = []
    for t in tasks:
        if t.started_at is None:
            continue
        running = run_models.status_str(t.status) == run_models.TaskStatus.running.value
        end = t.finished_at or (now if running else t.updated_at)
        if end is not None and end > t.started_at:
            spans.append((t.started_at, end))
    total = 0.0
    current = None
    for start, end in sorted(spans):
        if current and start <= current[1]:
            current = (current[0], max(current[1], end))
            continue
        if current:
            total += (current[1] - current[0]).total_seconds()
        current = (start, end)
    if current:
        total += (current[1] - current[0]).total_seconds()
    return total


async def run_usage(session: AsyncSession, user_id: str, run_id: str) -> dict:
    run = await get_run_or_404(session, run_id, user_id)
    tasks = (
        (
            await session.execute(
                select(run_models.ResearchTask).where(
                    run_models.ResearchTask.run_id == run_id
                )
            )
        )
        .scalars()
        .all()
    )
    by_status: dict[str, int] = {}
    input_tokens = output_tokens = turns = cache_read = 0
    model_seconds = tool_seconds = 0.0
    models: dict[tuple[str, str], dict] = {}
    paths: dict[str, int] = {}
    fallbacks: dict[str, int] = {}
    skips: dict[str, int] = {}
    for task in tasks:
        status = run_models.status_str(task.status)
        by_status[status] = by_status.get(status, 0) + 1
        input_tokens += task.input_tokens or 0
        output_tokens += task.output_tokens or 0
        turns += task.turns or 0
        cache_read += task.cache_read_tokens or 0
        model_seconds += task.model_seconds or 0.0
        tool_seconds += task.tool_seconds or 0.0
        if task.model or task.provider:
            row = models.setdefault(
                (task.provider or "", task.model or ""),
                {"provider": task.provider, "model": task.model, "tasks": 0, "input_tokens": 0, "output_tokens": 0},
            )
            row["tasks"] += 1
            row["input_tokens"] += task.input_tokens or 0
            row["output_tokens"] += task.output_tokens or 0
        if task.path:
            paths[task.path] = paths.get(task.path, 0) + 1
            if task.path == "agent":
                reason = task.path_reason or "unknown"
                fallbacks[reason] = fallbacks.get(reason, 0) + 1
            elif task.path == "skipped":
                reason = task.path_reason or "unknown"
                skips[reason] = skips.get(reason, 0) + 1
    candidates, first_at = (
        await session.execute(
            select(
                func.count(candidate_models.CandidateScore.id),
                func.min(candidate_models.CandidateScore.created_at),
            ).where(candidate_models.CandidateScore.run_id == run_id)
        )
    ).one()
    first_candidate_seconds = (
        max(0.0, (first_at - run.created_at).total_seconds())
        if first_at is not None and run.created_at is not None
        else None
    )
    tools: dict[str, dict[str, int]] = {}
    task_ids = [t.id for t in tasks]
    if task_ids:
        rows = (
            await session.execute(
                select(
                    run_models.ToolCallLog.tool_name, run_models.ToolCallLog.ok
                ).where(run_models.ToolCallLog.task_id.in_(task_ids))
            )
        ).all()
        for name, ok in rows:
            stat = tools.setdefault(name, {"calls": 0, "errors": 0})
            stat["calls"] += 1
            if ok is False:
                stat["errors"] += 1
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "turns": turns,
        "tasks": by_status,
        "tools": tools,
        "cache_read_tokens": cache_read,
        "model_seconds": round(model_seconds, 1),
        "tool_seconds": round(tool_seconds, 1),
        "models": sorted(models.values(), key=lambda m: -(m["input_tokens"] + m["output_tokens"])),
        "candidates": candidates,
        "tokens_per_candidate": (
            round((input_tokens + output_tokens) / candidates) if candidates else None
        ),
        "first_candidate_seconds": first_candidate_seconds,
        "active_seconds": round(active_seconds(tasks, utcnow_naive())),
        "narrow_paths": paths,
        "narrow_fallbacks": fallbacks,
        "narrow_skips": skips,
    }


def sse_frame(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


#: Without these, proxies (nginx especially) buffer or cache the stream and the feed looks dead.
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

#: Floor for EventSource's own retry; the client adds its own backoff.
SSE_RETRY_MS = 3000

#: Each stream holds a LISTEN connection outside the pool; lazy since a Semaphore binds to its loop.
_stream_slots: asyncio.Semaphore | None = None
_stream_slots_capacity = 0


def stream_slots() -> asyncio.Semaphore:
    global _stream_slots, _stream_slots_capacity
    if _stream_slots is None or _stream_slots_capacity != settings.sse_max_streams:
        _stream_slots = asyncio.Semaphore(settings.sse_max_streams)
        _stream_slots_capacity = settings.sse_max_streams
    return _stream_slots


# Explicit column lists, never `select(Model)`: `log` and `messages_json` run to hundreds of KB per
# row and the sweep runs per stream. `log` is probed by length; its text is fetched only while running.
_TASK_SWEEP_COLUMNS = (
    run_models.ResearchTask.id,
    run_models.ResearchTask.task_type,
    run_models.ResearchTask.target_name,
    run_models.ResearchTask.status,
    run_models.ResearchTask.turns,
    run_models.ResearchTask.error,
    func.coalesce(func.length(run_models.ResearchTask.log), 0),
)

_CANDIDATE_SWEEP_COLUMNS = (
    candidate_models.CandidateScore.id,
    candidate_models.CandidateScore.status,
    candidate_models.CandidateScore.similarity_score,
)


async def run_events(run_id: str, user_id: str, poll_interval: float | None = None):
    """Stream a run's changes over SSE, rechecking only the sections pg_notify woke.

    `done` is data, not the end: a run's queue can refill, so the client closes the stream.
    `poll_interval` is the sweep backstop for missed wakes and direct DB writes.
    """
    if poll_interval is None:
        poll_interval = settings.sse_sweep_seconds
    trace_cap = max(1, settings.sse_trace_max_events)

    # Recheck ownership: the run may have been deleted or changed hands since the route checked.
    async with SessionLocal() as _session:
        owner = (
            await _session.execute(
                select(run_models.Run.user_id).where(run_models.Run.id == run_id)
            )
        ).scalar_one_or_none()
    if owner != user_id:
        return

    seen_tasks: dict[str, tuple] = {}
    # Per task: last seen `log` length and entries pushed, so a growing trace emits only the tail.
    seen_log_len: dict[str, int] = {}
    sent_trace: dict[str, int] = {}
    seen_candidates: dict[str, tuple] = {}
    seen_drafts: dict[str, tuple] = {}
    seen_run_status: str | None = None
    done_sent = False

    async def check_tasks(session: AsyncSession) -> tuple[list[str], bool]:
        frames: list[str] = []
        rows = (
            await session.execute(
                select(*_TASK_SWEEP_COLUMNS).where(
                    run_models.ResearchTask.run_id == run_id
                )
            )
        ).all()
        open_tasks = False
        # Collected so the log text is fetched in one query.
        grew: list[str] = []
        for task_id, task_type, target_name, status, turns, error, log_len in rows:
            status_value = run_models.status_str(status)
            state = (status_value, turns, target_name, error)
            if seen_tasks.get(task_id) != state:
                seen_tasks[task_id] = state
                # Mirrors BoardTaskOut so clients can patch caches without refetching.
                frames.append(
                    sse_frame(
                        "task",
                        {
                            "id": task_id,
                            "task_type": task_type,
                            "target_name": target_name,
                            "status": status_value,
                            "turns": turns,
                            "error": error,
                        },
                    )
                )
            inflight = run_models.is_inflight_status(status)
            if inflight:
                open_tasks = True
                # A concluded task's log arrives with the REST row.
                if seen_log_len.get(task_id) != log_len:
                    seen_log_len[task_id] = log_len
                    if log_len:
                        grew.append(task_id)
                    elif sent_trace.pop(task_id, 0):
                        # Rerun cleared `log`; reset, or the client keeps the old attempt's trace.
                        frames.append(
                            sse_frame(
                                "trace",
                                {
                                    "id": task_id,
                                    "from": 0,
                                    "total": 0,
                                    "events": [],
                                },
                            )
                        )
            else:
                seen_log_len.pop(task_id, None)
                sent_trace.pop(task_id, None)

        if grew:
            logs = (
                await session.execute(
                    select(
                        run_models.ResearchTask.id, run_models.ResearchTask.log
                    ).where(run_models.ResearchTask.id.in_(grew))
                )
            ).all()
            for task_id, raw in logs:
                events = parse_task_log(raw) or []
                already = sent_trace.get(task_id, 0)
                if len(events) <= already:
                    # Log rewritten shorter (rerun): resend from scratch.
                    if len(events) == already:
                        continue
                    already = 0
                tail = events[already:][-trace_cap:]
                if not tail:
                    continue
                sent_trace[task_id] = len(events)
                frames.append(
                    sse_frame(
                        "trace",
                        {
                            "id": task_id,
                            # The client appends on a delta and replaces on 0.
                            "from": len(events) - len(tail),
                            "total": len(events),
                            "events": tail,
                        },
                    )
                )
        return frames, open_tasks

    async def check_candidates(session: AsyncSession) -> list[str]:
        frames: list[str] = []
        rows = (
            await session.execute(
                select(*_CANDIDATE_SWEEP_COLUMNS).where(
                    candidate_models.CandidateScore.run_id == run_id
                )
            )
        ).all()
        for candidate_id, status, score in rows:
            state = (run_models.status_str(status), score)
            if seen_candidates.get(candidate_id) != state:
                seen_candidates[candidate_id] = state
                frames.append(
                    sse_frame(
                        "candidate",
                        {
                            "id": candidate_id,
                            "status": state[0],
                            "similarity_score": score,
                        },
                    )
                )
        return frames

    async def check_drafts(session: AsyncSession) -> list[str]:
        frames: list[str] = []
        drafts = (
            await session.execute(
                select(
                    outreach_models.EmailDraft.id,
                    outreach_models.EmailDraft.candidate_id,
                    outreach_models.EmailDraft.subject,
                ).where(
                    outreach_models.EmailDraft.candidate_id.in_(
                        select(candidate_models.CandidateScore.id).where(
                            candidate_models.CandidateScore.run_id == run_id
                        )
                    )
                )
            )
        ).all()
        for draft_id, candidate_id, subject in drafts:
            state = (subject,)
            if seen_drafts.get(draft_id) != state:
                seen_drafts[draft_id] = state
                frames.append(
                    sse_frame(
                        "draft",
                        {
                            "id": draft_id,
                            "candidate_id": candidate_id,
                            "subject": subject,
                        },
                    )
                )
        return frames

    async def check_run_status(session: AsyncSession) -> str | None:
        return (
            await session.execute(
                select(run_models.Run.status).where(run_models.Run.id == run_id)
            )
        ).scalar_one_or_none()

    woke: asyncio.Queue[str] = asyncio.Queue()

    def _on_notify(_conn, _pid, _channel, payload: str) -> None:
        woke.put_nowait(payload)

    async def await_sections() -> set[str]:
        """Sections woken since the last check; all of them on sweep or without LISTEN."""
        if conn is None:
            await asyncio.sleep(poll_interval)
            return {"tasks", "candidates", "drafts"}
        try:
            first = await asyncio.wait_for(woke.get(), timeout=poll_interval)
            payloads = [first]
        except TimeoutError:
            return {"tasks", "candidates", "drafts"}
        while True:
            try:
                payloads.append(woke.get_nowait())
            except asyncio.QueueEmpty:
                break
        sections = set()
        for payload in payloads:
            parsed = parse_payload(payload)
            if parsed is None or parsed[0] != run_id:
                continue
            # For the feed, "work" means the same as "tasks".
            sections.add("tasks" if parsed[1] == "work" else parsed[1])
        return sections

    conn = None
    slots = stream_slots()
    await slots.acquire()
    try:
        try:
            conn = await asyncpg.connect(listener_dsn())
            await conn.add_listener(CHANNEL, _on_notify)
        except Exception:  # noqa: BLE001 - LISTEN is an optimization; the sweep covers
            conn = None
        # Its own frame, so it never rides along with an event payload.
        yield f"retry: {SSE_RETRY_MS}\n\n"
        # Full sync first: covers changes before LISTEN attached.
        sections = {"tasks", "candidates", "drafts"}
        while True:
            # Yield only after the session is released: yielding inside it pins a pooled connection
            # while the client reads, and hands a disconnect's CancelledError to __aexit__.
            frames: list[str] = []
            # None = "not rechecked this pass", not "no open tasks" (else duplicate done frames).
            open_tasks: bool | None = None
            async with SessionLocal() as session:
                if "tasks" in sections:
                    task_frames, open_tasks = await check_tasks(session)
                    frames.extend(task_frames)
                if "candidates" in sections:
                    frames.extend(await check_candidates(session))
                if "drafts" in sections:
                    frames.extend(await check_drafts(session))
                status = await check_run_status(session)
            if status is None:
                # Run deleted underneath the stream.
                return
            if status != seen_run_status:
                seen_run_status = status
                frames.append(sse_frame("run_status", {"run_id": run_id, "status": status}))
            if open_tasks is True:
                done_sent = False
            elif open_tasks is False and not done_sent:
                done_sent = True
                frames.append(sse_frame("done", {"run_id": run_id}))
            for frame in frames:
                yield frame
            yield ": ping\n\n"
            sections = await await_sections()
    finally:
        slots.release()
        if conn is not None:
            try:
                await conn.remove_listener(CHANNEL, _on_notify)
            except Exception as exc:  # noqa: BLE001 - closing anyway; report and move on
                print(f"[events] listener cleanup: {exc}", flush=True)
            await conn.close()


def parse_task_log(raw: str | None) -> list[dict] | None:
    if not raw:
        return None
    try:
        events = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return events if isinstance(events, list) else None


def parse_blob(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
