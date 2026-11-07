"""HTTP-facing task reads and mutations; queue mechanics live in api/runs/queue.py."""

from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.exceptions import BadRequestError, NotFoundError
from api.core.time import duration_seconds, utcnow_naive
from api.runs import models as run_models
from api.runs.lifecycle import note_tasks_drained, note_work_enqueued
from api.runs.service import (
    get_run_or_404,
    parse_blob,
    parse_task_log,
)


async def find_inflight_draft_tasks(
    session: AsyncSession, user_id: str, candidate_ids: Sequence[str]
) -> dict[str, run_models.ResearchTask]:
    """Newest pending/running draft_email task per candidate id."""
    if not candidate_ids:
        return {}
    rows = (
        (
            await session.execute(
                select(run_models.ResearchTask)
                .where(
                    run_models.ResearchTask.user_id == user_id,
                    run_models.ResearchTask.task_type == "draft_email",
                    run_models.ResearchTask.target_id.in_(candidate_ids),
                    run_models.ResearchTask.status.in_(
                        run_models.INFLIGHT_TASK_STATUSES
                    ),
                )
                .order_by(run_models.ResearchTask.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    inflight: dict[str, run_models.ResearchTask] = {}
    for task in rows:
        if task.target_id is not None and task.target_id not in inflight:
            inflight[task.target_id] = task
    return inflight


def task_out_dict(t: run_models.ResearchTask) -> dict:
    return {
        "id": t.id,
        "task_type": t.task_type,
        "target_id": t.target_id,
        "target_name": t.target_name,
        "status": run_models.status_str(t.status),
        "error": t.error,
        "turns": t.turns,
        "final_text": t.final_text,
        "log": parse_task_log(t.log),
        "input_tokens": t.input_tokens,
        "output_tokens": t.output_tokens,
        "started_at": t.started_at,
        "finished_at": t.finished_at,
        "duration_seconds": duration_seconds(t.created_at, t.updated_at),
        "updated_at": t.updated_at,
    }


def board_task_out_dict(t: run_models.ResearchTask) -> dict:
    return {
        "id": t.id,
        "task_type": t.task_type,
        "target_name": t.target_name,
        "status": run_models.status_str(t.status),
        "turns": t.turns,
        "error": t.error,
        "updated_at": t.updated_at,
    }


def validate_task_filter(status: str | None, sort: str) -> None:
    if sort not in ("created", "recent"):
        raise BadRequestError("sort must be 'created' or 'recent'")
    if status is not None and status not in {s.value for s in run_models.TaskStatus}:
        raise BadRequestError(f"Unknown task status: {status}")


async def get_task_or_404(
    session: AsyncSession, task_id: str, user_id: str
) -> run_models.ResearchTask:
    task = (
        (
            await session.execute(
                select(run_models.ResearchTask).where(
                    run_models.ResearchTask.id == task_id,
                    run_models.ResearchTask.user_id == user_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if not task:
        raise NotFoundError("Task not found")
    return task


async def list_tasks(
    session: AsyncSession,
    user_id: str,
    run_id: str,
    *,
    status: str | None = None,
    task_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
    sort: str = "created",
) -> tuple[list[dict], int]:
    """Returns (items, total before paging)."""
    validate_task_filter(status, sort)
    await get_run_or_404(session, run_id, user_id)
    filters = [
        run_models.ResearchTask.run_id == run_id,
        run_models.ResearchTask.user_id == user_id,
    ]
    if status is not None:
        filters.append(run_models.ResearchTask.status == run_models.TaskStatus(status))
    if task_type is not None:
        filters.append(run_models.ResearchTask.task_type == task_type)
    total = (
        await session.execute(
            select(func.count()).select_from(run_models.ResearchTask).where(*filters)
        )
    ).scalar() or 0
    # A batch shares created_at; the id tie-break keeps offset pages stable.
    created, task_id = run_models.ResearchTask.created_at, run_models.ResearchTask.id
    order = (created, task_id) if sort == "created" else (created.desc(), task_id.desc())
    result = await session.execute(
        select(run_models.ResearchTask)
        .where(*filters)
        .order_by(*order)
        .offset(offset)
        .limit(limit)
    )
    return [task_out_dict(t) for t in result.scalars().all()], total


async def get_board(session: AsyncSession, user_id: str, run_id: str) -> dict:
    await get_run_or_404(session, run_id, user_id)
    result = await session.execute(
        select(run_models.ResearchTask)
        .where(run_models.ResearchTask.run_id == run_id)
        .order_by(run_models.ResearchTask.created_at.desc())
    )
    columns: dict[str, list[dict]] = {s.value: [] for s in run_models.TaskStatus}
    for task in result.scalars().all():
        columns[run_models.status_str(task.status)].append(board_task_out_dict(task))
    return columns


async def get_task(session: AsyncSession, user_id: str, task_id: str) -> dict:
    return task_out_dict(await get_task_or_404(session, task_id, user_id))


async def delete_task(session: AsyncSession, user_id: str, task_id: str) -> dict:
    """A running task can't be deleted (the worker holds the row): cancel it first."""
    task = await get_task_or_404(session, task_id, user_id)
    if run_models.status_str(task.status) == run_models.TaskStatus.running.value:
        raise BadRequestError("Task is running; cancel it before deleting")
    await session.execute(
        delete(run_models.ToolCallLog).where(run_models.ToolCallLog.task_id == task_id)
    )
    await session.execute(
        delete(run_models.ResearchTask).where(run_models.ResearchTask.id == task_id)
    )
    await session.commit()
    # Pruning the last open task can conclude the run.
    await note_tasks_drained(session, task.run_id)
    await session.commit()
    return {"status": "deleted"}


async def _refuse_if_agent_cancelled(session: AsyncSession, task) -> None:
    from api.runs.agents import is_cancelled

    run = await session.get(run_models.Run, task.run_id)
    if run is not None and is_cancelled(run, task.task_type):
        raise BadRequestError("This agent is cancelled for the run; resume the agent to run its tasks again.")


async def retry_task(session: AsyncSession, user_id: str, task_id: str) -> dict:
    """Requeue an `error` task; its checkpoint is kept so it resumes."""
    task = await get_task_or_404(session, task_id, user_id)
    status = run_models.status_str(task.status)
    if status != run_models.TaskStatus.error.value:
        raise BadRequestError(f"Only error tasks can be retried (status={status})")
    await _refuse_if_agent_cancelled(session, task)
    task.status = run_models.TaskStatus.pending
    task.error = None
    task.finished_at = None
    await note_work_enqueued(session, task.run_id)
    await session.commit()
    return {"status": "pending"}


async def rerun_task(session: AsyncSession, user_id: str, task_id: str) -> dict:
    """Run a finished task again from scratch; re-saves hit the dedup paths, so nothing duplicates."""
    task = await get_task_or_404(session, task_id, user_id)
    status = run_models.status_str(task.status)
    if status not in (
        run_models.TaskStatus.done.value,
        run_models.TaskStatus.error.value,
        run_models.TaskStatus.cancelled.value,
    ):
        raise BadRequestError(
            f"Only done, error, or cancelled tasks can be rerun (status={status})"
        )
    await _refuse_if_agent_cancelled(session, task)
    await session.execute(
        delete(run_models.ToolCallLog).where(run_models.ToolCallLog.task_id == task_id)
    )
    task.status = run_models.TaskStatus.pending
    task.error = None
    task.log = None
    task.final_text = None
    task.turns = None
    task.input_tokens = None
    task.output_tokens = None
    task.messages_json = None
    task.started_at = None
    task.finished_at = None
    await note_work_enqueued(session, task.run_id)
    await session.commit()
    return {"status": "pending"}


async def pause_task(session: AsyncSession, user_id: str, task_id: str) -> dict:
    """A running task is only marked; the worker honors it at conclude and keeps the checkpoint."""
    task = await get_task_or_404(session, task_id, user_id)
    status = run_models.status_str(task.status)
    if status not in (
        run_models.TaskStatus.pending.value,
        run_models.TaskStatus.running.value,
    ):
        raise BadRequestError(f"Only pending or running tasks can pause (status={status})")
    task.status = run_models.TaskStatus.paused
    await session.commit()
    await note_tasks_drained(session, task.run_id)
    await session.commit()
    return {"status": "paused"}


async def resume_task(session: AsyncSession, user_id: str, task_id: str) -> dict:
    task = await get_task_or_404(session, task_id, user_id)
    status = run_models.status_str(task.status)
    if status != run_models.TaskStatus.paused.value:
        raise BadRequestError(f"Only paused tasks can resume (status={status})")
    task.status = run_models.TaskStatus.pending
    task.finished_at = None
    await note_work_enqueued(session, task.run_id)
    await session.commit()
    return {"status": "pending"}


async def cancel_task(session: AsyncSession, user_id: str, task_id: str) -> dict:
    """A running task is only marked; the worker honors it at conclude."""
    task = await get_task_or_404(session, task_id, user_id)
    status = run_models.status_str(task.status)
    if status not in (
        run_models.TaskStatus.pending.value,
        run_models.TaskStatus.paused.value,
        run_models.TaskStatus.running.value,
        run_models.TaskStatus.deferred.value,
    ):
        raise BadRequestError(
            f"Only pending, paused, running, or waiting tasks can cancel (status={status})"
        )
    task.status = run_models.TaskStatus.cancelled
    # Ends the attempt now; the worker's later conclude for it is skipped.
    task.finished_at = utcnow_naive()
    await session.commit()
    await note_tasks_drained(session, task.run_id)
    await session.commit()
    return {"status": "cancelled"}


async def list_tool_calls(session: AsyncSession, user_id: str, task_id: str) -> list[dict]:
    await get_task_or_404(session, task_id, user_id)
    result = await session.execute(
        select(run_models.ToolCallLog)
        .where(run_models.ToolCallLog.task_id == task_id)
        .order_by(run_models.ToolCallLog.turn)
    )
    return [
        {
            "turn": log.turn,
            "tool_name": log.tool_name,
            "input": parse_blob(log.input_json),
            "result": parse_blob(log.result_json),
            "ok": log.ok,
        }
        for log in result.scalars().all()
    ]
