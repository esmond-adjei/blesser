"""Prune agent traces (they hold fetched pages and interest-derived queries) after TRACE_RETENTION_DAYS."""

from datetime import timedelta

from sqlalchemy import delete, select, update

from api.core.config import settings
from api.core.time import utcnow_naive
from api.runs import models as run_models

_FINISHED = (
    run_models.TaskStatus.done,
    run_models.TaskStatus.error,
    run_models.TaskStatus.cancelled,
)


async def prune_traces(session, days: int | None = None) -> dict:
    """Returns counts; a no-op when retention is off (<= 0)."""
    days = settings.trace_retention_days if days is None else days
    if days <= 0:
        return {"tool_calls": 0, "tasks": 0}
    cutoff = utcnow_naive() - timedelta(days=days)
    task = run_models.ResearchTask
    old_tasks = (
        task.status.in_(_FINISHED),
        task.finished_at.is_not(None),
        task.finished_at < cutoff,
    )
    logs = await session.execute(
        delete(run_models.ToolCallLog).where(
            run_models.ToolCallLog.task_id.in_(_old_task_ids(cutoff))
        )
    )
    tasks = await session.execute(
        update(task)
        .where(*old_tasks, (task.log.is_not(None)) | (task.messages_json.is_not(None)))
        .values(log=None, messages_json=None)
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    return {"tool_calls": logs.rowcount or 0, "tasks": tasks.rowcount or 0}


def _old_task_ids(cutoff):
    task = run_models.ResearchTask
    return select(task.id).where(
        task.status.in_(_FINISHED),
        task.finished_at.is_not(None),
        task.finished_at < cutoff,
    )
