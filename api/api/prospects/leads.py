"""Fair-share release of professor leads across a run's programmes.

Every name is stored as a `deferred` narrow task so the first programmes
to finish can't take the whole candidate cap. Leads move to `pending`:

- only while saved candidates plus open narrow tasks stay under the cap;
- while some supervisors haven't answered, each programme gets at most a
  fair share, the rest held back for them;
- fewest-researched programme first, best name first, up to the
  per-programme dial;
- a task ending without a save, or failing, frees its slot;
- a programme whose last PROGRAMME_MISS_STREAK professors all scored
  unrelated gets no more (leads are ranked by topic, so the rest are less
  likely); held leads get path "skipped" / "tail_stop" until a later save
  breaks the streak.

Total research is bounded by `research_budget_factor` x the candidate cap.
"""

import json
import math

from sqlalchemy import func, select, update

from api.candidates import models as candidate_models
from api.core.config import settings
from api.runs import models as run_models
from api.runs.budgets import run_limit
from api.runs.notify import notify_work

NARROW = "research_one_professor"
SUPERVISOR = "research_professor"

_OPEN = {run_models.TaskStatus.pending.value, run_models.TaskStatus.running.value}
_DEFERRED = run_models.TaskStatus.deferred.value
_ERROR = run_models.TaskStatus.error.value
_DONE = run_models.TaskStatus.done.value

#: Note on a lead held back because its programme kept missing.
MISS_STREAK_NOTE = "Not researched: "
#: path_reason of such a lead, next to "run_cap" in the usage view.
TAIL_STOP = "tail_stop"


async def _missing_programmes(session, released) -> dict[str | None, int]:
    """{programme: streak} for programmes whose latest PROGRAMME_MISS_STREAK
    professors ended in confirm_no_match/low_score with no save between.
    Other outcomes and user-added professors say nothing about the topic,
    so they neither count nor break a streak."""
    k = settings.programme_miss_streak
    finished = [
        t
        for t in released
        if run_models.status_str(t.status) == _DONE and t.path_reason != "user_added"
    ]
    if k <= 0 or len(finished) < k:
        return {}
    log = run_models.ToolCallLog
    rows = (
        await session.execute(
            select(log.task_id, log.tool_name, log.input_json).where(
                log.task_id.in_([t.id for t in finished]),
                log.tool_name.in_(["save_professor_record", "confirm_no_match"]),
                log.ok.is_not(False),
            )
        )
    ).all()
    outcome: dict[str, str] = {}
    for row in rows:
        if row.tool_name == "save_professor_record":
            outcome[row.task_id] = "saved"
        elif outcome.get(row.task_id) != "saved":
            try:
                code = json.loads(row.input_json or "{}").get("reason_code")
            except (TypeError, ValueError, AttributeError):
                code = None
            outcome[row.task_id] = "miss" if code == "low_score" else "other"
    by_programme: dict[str | None, list] = {}
    for t in finished:
        by_programme.setdefault(t.target_id, []).append(t)
    stopped: dict[str | None, int] = {}
    for programme, tasks in by_programme.items():
        streak = 0
        for t in sorted(tasks, key=lambda t: t.finished_at or t.created_at, reverse=True):
            result = outcome.get(t.id)
            if result == "saved":
                break
            if result == "miss":
                streak += 1
                if streak >= k:
                    stopped[programme] = streak
                    break
    return stopped


async def run_candidate_room(session, run, user_id: str) -> tuple[int, int]:
    """(candidate cap, candidates saved) for a run."""
    limit = run_limit(run, "max_professors", settings.max_candidates_per_run)
    saved = (
        await session.execute(
            select(func.count())
            .select_from(candidate_models.CandidateScore)
            .where(
                candidate_models.CandidateScore.run_id == run.id,
                candidate_models.CandidateScore.user_id == user_id,
            )
        )
    ).scalar() or 0
    return limit, int(saved)


def research_budget(cap: int) -> int:
    """Most narrow tasks a run may research: the cap plus room for non-matches."""
    return max(cap, math.ceil(cap * settings.research_budget_factor))


async def release_deferred_leads(session, run_id: str) -> int:
    """Returns how many leads were released. Does not commit."""
    # Row lock: two workers concluding tasks at once would release the same room twice.
    run = (
        await session.execute(
            select(run_models.Run).where(run_models.Run.id == run_id).with_for_update()
        )
    ).scalar_one_or_none()
    if run is None or run.status != "running":
        return 0
    from api.runs.agents import held_types

    if NARROW in held_types(run):
        return 0
    task = run_models.ResearchTask
    # Columns only: task rows carry trace payloads, and this runs on every conclusion.
    rows = (
        await session.execute(
            select(
                task.id,
                task.task_type,
                task.target_id,
                task.status,
                task.finished_at,
                task.created_at,
                task.path_reason,
            )
            .where(
                task.run_id == run_id,
                task.user_id == run.user_id,
                task.task_type.in_([NARROW, SUPERVISOR]),
            )
            .order_by(task.created_at, task.id)
        )
    ).all()
    narrow = [t for t in rows if t.task_type == NARROW]
    waiting = [t for t in narrow if run_models.status_str(t.status) == _DEFERRED]
    if not waiting:
        return 0

    cap, saved = await run_candidate_room(session, run, run.user_id)
    released = [t for t in narrow if run_models.status_str(t.status) != _DEFERRED]
    open_count = sum(1 for t in released if run_models.status_str(t.status) in _OPEN)
    with_leads = {t.target_id for t in narrow}
    programmes = with_leads | {t.target_id for t in rows if t.task_type == SUPERVISOR}
    # Keep a fair share for supervisors still working.
    pending_supervisors = {
        t.target_id
        for t in rows
        if t.task_type == SUPERVISOR
        and run_models.status_str(t.status) in _OPEN
        and t.target_id not in with_leads
    }
    per_programme = run_limit(
        run, "max_professors_per_program", settings.max_professors_per_program
    )
    free = cap - saved
    fair = min(per_programme, max(1, free // max(len(programmes), 1)))
    room = min(
        free - open_count - fair * len(pending_supervisors),
        research_budget(cap) - len(released),
    )
    if room <= 0:
        return 0

    # A failed task doesn't use its programme's share; the research budget still bounds cost.
    used: dict[str | None, int] = {}
    for t in released:
        if run_models.status_str(t.status) != _ERROR:
            used[t.target_id] = used.get(t.target_id, 0) + 1
    queues: dict[str | None, list] = {}
    for t in waiting:
        queues.setdefault(t.target_id, []).append(t)
    stopped = await _missing_programmes(session, released)
    held = [t.id for p in stopped for t in queues.pop(p, [])]
    if held:
        # The note explains unresearched names on the board and "not saved" view.
        await session.execute(
            update(task)
            .where(task.id.in_(held), task.status == run_models.TaskStatus.deferred, task.error.is_(None))
            .values(
                path="skipped",
                path_reason=TAIL_STOP,
                error=(
                    f"{MISS_STREAK_NOTE}the last {settings.programme_miss_streak} professors "
                    "researched at this programme scored as unrelated, and the rest of its "
                    "list ranks lower on the topic."
                )
            )
        )
    order = list(queues)
    # Fair share until every supervisor has answered, then up to the per-programme dial.
    share = fair if pending_supervisors else per_programme

    chosen: list[str] = []
    while room > 0:
        eligible = [p for p in order if queues[p] and used.get(p, 0) < share]
        if not eligible:
            break
        programme = min(eligible, key=lambda p: used.get(p, 0))
        chosen.append(queues[programme].pop(0).id)
        used[programme] = used.get(programme, 0) + 1
        room -= 1
    if chosen:
        await session.execute(
            update(task)
            .where(task.id.in_(chosen), task.status == run_models.TaskStatus.deferred)
            # A lead held by a streak that a later save broke loses its note.
            .values(status=run_models.TaskStatus.pending, error=None, path=None, path_reason=None)
        )
        await notify_work(session, run_id)
    return len(chosen)
