"""Notification event sites: one function per kind of event.

Each runs inside the causing change's transaction and never commits. Text goes
through the browser vendor's push service, so never include CV text, draft
content or professor details (tests/test_notifications.py checks).
"""

from sqlalchemy import func, select, text

from api.core.time import utcnow_naive
from api.notifications.service import notify
from api.runs import models as run_models


def run_title(run: run_models.Run) -> str:
    """Same wording as the web app's runTitle: field in region."""
    if run.region == "(preselected list)":
        return "Preselected programs"
    field = (run.field or "").strip() or "Your search"
    return f"{field} in {run.region}" if run.region else f"{field}, anywhere"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


async def run_finished(session, run: run_models.Run) -> bool:
    """Keyed on the research task count: reopened drafts don't re-announce, more research does."""
    from api.candidates import models as candidate_models

    research_tasks = (
        await session.execute(
            select(func.count())
            .select_from(run_models.ResearchTask)
            .where(
                run_models.ResearchTask.run_id == run.id,
                run_models.ResearchTask.task_type != "draft_email",
            )
        )
    ).scalar() or 0
    candidates = (
        await session.execute(
            select(func.count())
            .select_from(candidate_models.CandidateScore)
            .where(candidate_models.CandidateScore.run_id == run.id)
        )
    ).scalar() or 0
    return await notify(
        session,
        user_id=run.user_id,
        kind="run_finished",
        title="Run finished",
        body=f"Your run {run_title(run)} finished: {_plural(candidates, 'candidate')}.",
        link=f"/runs/{run.id}",
        entity_id=run.id,
        dedupe_key=f"run:{run.id}:done:{research_tasks}",
    )


async def first_candidate(session, run: run_models.Run, candidate_id: str | None = None) -> bool:
    """Only the first candidate of a run notifies (via the dedupe key)."""
    return await notify(
        session,
        user_id=run.user_id,
        kind="first_candidate",
        title="First candidate saved",
        body=f"Your run {run_title(run)} saved its first candidate.",
        link=f"/runs/{run.id}" + (f"?preview={candidate_id}" if candidate_id else ""),
        entity_id=run.id,
        dedupe_key=f"run:{run.id}:first_candidate",
    )


async def run_paused(session, run: run_models.Run, task_id: str, attempt: int) -> bool:
    """Called only by the attempt whose update paused the run, so it notifies once."""
    return await notify(
        session,
        user_id=run.user_id,
        kind="run_paused",
        title="Run paused",
        body=(
            f"Your run {run_title(run)} paused: the model allowance ran out. "
            "Resume it once there is allowance again."
        ),
        link=f"/runs/{run.id}",
        entity_id=run.id,
        dedupe_key=f"run:{run.id}:paused:{task_id}:{attempt}",
    )


async def run_attention(session, run: run_models.Run, task_type: str | None = None) -> bool:
    """A task failed for good. At most one a day per run."""
    day = utcnow_naive().date().isoformat()
    return await notify(
        session,
        user_id=run.user_id,
        kind="run_attention",
        title="Run needs attention",
        body=f"A task in your run {run_title(run)} failed after its retries.",
        link=f"/runs/{run.id}" + (f"?tab={task_type}&status=error" if task_type else ""),
        entity_id=run.id,
        dedupe_key=f"run:{run.id}:attention:{day}",
    )


async def drafts_ready(session, run: run_models.Run, task_id: str, attempt: int) -> bool:
    """Notify when the last open draft task of the run finishes. The advisory lock
    serialises concluding tasks, so the last of two finishing together sees the other done."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"drafts:{run.id}"},
    )
    still_open = (
        await session.execute(
            select(func.count())
            .select_from(run_models.ResearchTask)
            .where(
                run_models.ResearchTask.run_id == run.id,
                run_models.ResearchTask.task_type == "draft_email",
                run_models.ResearchTask.id != task_id,
                run_models.ResearchTask.status.in_(run_models.INFLIGHT_TASK_STATUSES),
            )
        )
    ).scalar() or 0
    if still_open:
        return False
    return await notify(
        session,
        user_id=run.user_id,
        kind="drafts_ready",
        title="Email drafts ready",
        body=f"The email drafts you asked for in {run_title(run)} are ready to review.",
        link="/outbox",
        entity_id=run.id,
        dedupe_key=f"drafts:{task_id}:{attempt}",
    )
