"""Pause, resume or cancel one agent (task type) in a run while the rest carries on.

Enforced where work starts: the claim query skips held agents, and every enqueue
site (via note_work_enqueued) holds new tasks, so no spawn path can bypass a pause.
A paused agent keeps the run open; a cancelled one doesn't, until resumed.
"""

import json

from sqlalchemy import func, select, update

from api.agents.registry import TASK_TYPES
from api.core.exceptions import BadRequestError
from api.core.time import utcnow_naive
from api.runs import models as run_models

PAUSED = "paused"
CANCELLED = "cancelled"

CANCELLED_NOTE = "Agent cancelled for this run."

#: Work asked for by hand, so it runs while the run is halted; its own agent's state still holds it.
OUTLIVES_RUN_HALT = frozenset({"draft_email"})


def agent_states(run) -> dict[str, str]:
    raw = getattr(run, "agent_states", None)
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return {k: v for k, v in value.items() if v in (PAUSED, CANCELLED)} if isinstance(value, dict) else {}


def held_types(run) -> list[str]:
    """Task types whose work must not start now."""
    return list(agent_states(run))


def _store(run, states: dict[str, str]) -> None:
    run.agent_states = json.dumps(states, sort_keys=True) if states else None


def _check(run, task_type: str) -> None:
    if task_type not in TASK_TYPES:
        raise BadRequestError(f"Unknown agent {task_type!r}.")


def _tasks(run_id: str, task_type: str, *statuses):
    task = run_models.ResearchTask
    return update(task).where(
        task.run_id == run_id,
        task.task_type == task_type,
        task.status.in_([run_models.TaskStatus(s) for s in statuses]),
    )


async def pause_agent(session, run, task_type: str) -> dict:
    _check(run, task_type)
    states = agent_states(run)
    if states.get(task_type) == CANCELLED:
        raise BadRequestError("This agent was cancelled for this run; it can't be paused.")
    states[task_type] = PAUSED
    _store(run, states)
    result = await session.execute(
        _tasks(run.id, task_type, "pending", "running").values(status=run_models.TaskStatus.paused)
    )
    return {"state": PAUSED, "affected": result.rowcount or 0}


async def resume_agent(session, run, task_type: str) -> dict:
    _check(run, task_type)
    states = agent_states(run)
    was_cancelled = states.pop(task_type, None) == CANCELLED
    _store(run, states)
    if was_cancelled:
        task = run_models.ResearchTask
        # Professor leads go back to waiting so the per-programme limits still apply.
        requeued = run_models.TaskStatus.deferred if task_type == "research_one_professor" else run_models.TaskStatus.pending
        result = await session.execute(
            _tasks(run.id, task_type, "cancelled")
            .where(task.error == CANCELLED_NOTE)
            .values(status=requeued, error=None, finished_at=None, started_at=None)
        )
        return {"state": None, "affected": result.rowcount or 0}
    result = await session.execute(
        _tasks(run.id, task_type, "paused").values(
            status=run_models.TaskStatus.pending, finished_at=None
        )
    )
    return {"state": None, "affected": result.rowcount or 0}


async def cancel_agent(session, run, task_type: str) -> dict:
    _check(run, task_type)
    states = agent_states(run)
    states[task_type] = CANCELLED
    _store(run, states)
    result = await session.execute(
        _tasks(run.id, task_type, "pending", "running", "paused", "deferred").values(
            status=run_models.TaskStatus.cancelled,
            finished_at=utcnow_naive(),
            error=CANCELLED_NOTE,
        )
    )
    return {"state": CANCELLED, "affected": result.rowcount or 0}


async def hold_new_work(session, run) -> None:
    """Give tasks just queued for a held agent its state."""
    for task_type, state in agent_states(run).items():
        if state == PAUSED:
            await session.execute(
                _tasks(run.id, task_type, "pending").values(status=run_models.TaskStatus.paused)
            )
        else:
            await session.execute(
                _tasks(run.id, task_type, "pending", "paused", "deferred").values(
                    status=run_models.TaskStatus.cancelled,
                    finished_at=utcnow_naive(),
                    error=CANCELLED_NOTE,
                )
            )


def is_cancelled(run, task_type: str) -> bool:
    return agent_states(run).get(task_type) == CANCELLED


async def paused_work(session, run) -> int:
    """Tasks held by a paused agent: they keep the run open, unlike tasks paused one by one."""
    paused = [t for t, s in agent_states(run).items() if s == PAUSED]
    if not paused:
        return 0
    task = run_models.ResearchTask
    return (
        await session.execute(
            select(func.count())
            .select_from(task)
            .where(
                task.run_id == run.id,
                task.task_type.in_(paused),
                task.status.in_([run_models.TaskStatus.paused, run_models.TaskStatus.deferred]),
            )
        )
    ).scalar() or 0
