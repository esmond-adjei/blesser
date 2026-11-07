"""Every running/done run transition. Nothing here commits: callers own the commit.

Only ever called with run ids from already-verified owned objects, never raw request ids.
"""

from sqlalchemy import func, select

from api.runs import models as run_models
from api.runs.notify import notify_tasks, notify_work


async def note_work_enqueued(session, run_id: str) -> None:
    """Reopen a `done` run when new work is enqueued; paused/cancelled runs need an explicit resume."""
    run = await session.get(run_models.Run, run_id)
    if run is not None:
        # New work for a paused or cancelled agent is held as it lands.
        from api.runs.agents import hold_new_work

        await hold_new_work(session, run)
    if run is not None and run.status == "done":
        run.status = "running"
    await notify_tasks(session, run_id)
    # Wake the worker too, so a chained task is claimed on commit, not the next poll.
    await notify_work(session, run_id)


async def note_tasks_drained(session, run_id: str) -> None:
    """Flip a running run to done once no task is open; the only way into done.

    Always wakes the feed: concludes, pauses, cancels and deletes all funnel through here.
    """
    run = await session.get(run_models.Run, run_id)
    if run is None or run.status != "running":
        await notify_tasks(session, run_id)
        return
    # A finished task may have freed a research slot for a waiting lead.
    from api.prospects.leads import release_deferred_leads

    await release_deferred_leads(session, run_id)
    open_tasks = (
        await session.execute(
            select(func.count())
            .select_from(run_models.ResearchTask)
            .where(
                run_models.ResearchTask.run_id == run_id,
                run_models.ResearchTask.status.in_(run_models.INFLIGHT_TASK_STATUSES),
            )
        )
    ).scalar() or 0
    if open_tasks == 0:
        # A paused agent's work isn't finished, only waiting.
        from api.runs.agents import paused_work

        open_tasks = await paused_work(session, run)
    if open_tasks == 0:
        run.status = "done"
        print(f"[worker] run {run_id[:8]} done (no open tasks)", flush=True)
        # Same transaction as the flip: a rolled-back conclude never notifies.
        from api.notifications import events as notification_events

        await notification_events.run_finished(session, run)
    await notify_tasks(session, run_id)
