"""Task routes: queue inspection, retry, prune, tool-call records."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.core.db import get_session
from api.core.ratelimit import rate_limit
from api.runs import schemas as run_schemas
from api.runs import task_service
from api.runs.health import check_workers

router = APIRouter(tags=["tasks"])
workers_router = APIRouter(tags=["workers"])


@router.get("/runs/{run_id}/tasks", response_model=list[run_schemas.TaskOut])
async def list_tasks(
    run_id: str,
    response: Response,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
    status: str | None = None,
    task_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="created"),
):
    """A run's tasks with their live traces; total in X-Total-Count."""
    items, total = await task_service.list_tasks(
        session, current.id, run_id, status=status, task_type=task_type, limit=limit, offset=offset, sort=sort
    )
    response.headers["X-Total-Count"] = str(total)
    return [run_schemas.TaskOut(**d) for d in items]


@router.get("/runs/{run_id}/board", response_model=run_schemas.BoardOut)
async def get_board(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Kanban columns of a run's tasks, without traces."""
    return run_schemas.BoardOut(**await task_service.get_board(session, current.id, run_id))


@router.get("/tasks/{task_id}", response_model=run_schemas.TaskOut)
async def get_task(
    task_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return run_schemas.TaskOut(**await task_service.get_task(session, current.id, task_id))


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Prune one task and its tool-call records."""
    return await task_service.delete_task(session, current.id, task_id)


@router.post("/tasks/{task_id}/retry", dependencies=[Depends(rate_limit("agent_work"))])
async def retry_task(
    task_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Requeue a failed (`error`) task; it resumes from its checkpoint."""
    return await task_service.retry_task(session, current.id, task_id)


@router.post("/tasks/{task_id}/rerun", dependencies=[Depends(rate_limit("agent_work"))])
async def rerun_task(
    task_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Run a finished task again from scratch."""
    return await task_service.rerun_task(session, current.id, task_id)


@router.post("/tasks/{task_id}/pause")
async def pause_task(
    task_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Pause a task; a running one stops at conclude and keeps its checkpoint."""
    return await task_service.pause_task(session, current.id, task_id)


@router.post("/tasks/{task_id}/resume")
async def resume_task(
    task_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Requeue a paused task; it resumes from its checkpoint."""
    return await task_service.resume_task(session, current.id, task_id)


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Cancel a pending, paused or running task."""
    return await task_service.cancel_task(session, current.id, task_id)


@router.get("/tasks/{task_id}/tool-calls", response_model=list[run_schemas.ToolCallOut])
async def list_tool_calls(
    task_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Full tool-call records for one task."""
    return [
        run_schemas.ToolCallOut(**d)
        for d in await task_service.list_tool_calls(session, current.id, task_id)
    ]


@workers_router.get("/workers", response_model=list[run_schemas.WorkerOut])
async def list_workers(
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Worker heartbeats, most recent first (global, not per-account)."""
    workers = (await check_workers())["workers"]
    return [run_schemas.WorkerOut(**w) for w in workers]
