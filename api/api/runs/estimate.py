"""What a run is likely to cost before it starts: a warning, never a gate."""

import math

from sqlalchemy import func, select

from api.auth.models import User
from api.billing import service as billing
from api.runs import models as run_models

#: Rough tokens per task until the person has their own history.
DEFAULT_TASK_TOKENS = {
    "discover_programs": 80_000,
    "research_professor": 30_000,
    "research_one_professor": 25_000,
}
#: Newest finished tasks of a type to average over.
HISTORY_TASKS = 200
MIN_HISTORY = 5
#: At most this many narrow tasks researched per candidate kept.
RESEARCH_FACTOR = 2.5


async def _averages(session, user_id: str) -> dict[str, int]:
    task = run_models.ResearchTask
    out: dict[str, int] = {}
    for task_type in DEFAULT_TASK_TOKENS:
        recent = (
            select((func.coalesce(task.input_tokens, 0) + func.coalesce(task.output_tokens, 0)).label("t"))
            .where(
                task.user_id == user_id,
                task.task_type == task_type,
                task.status == run_models.TaskStatus.done,
                task.input_tokens.is_not(None),
            )
            .order_by(task.created_at.desc())
            .limit(HISTORY_TASKS)
            .subquery()
        )
        count, avg = (
            await session.execute(select(func.count(), func.avg(recent.c.t)))
        ).one()
        if count and count >= MIN_HISTORY and avg is not None:
            out[task_type] = int(avg)
    return out


async def estimate_run(
    session,
    user_id: str,
    *,
    max_programs: int,
    max_professors: int,
    max_professors_per_program: int,
    llm_provider: str | None = None,
) -> dict:
    averages = await _averages(session, user_id)
    per_task = {t: averages.get(t, d) for t, d in DEFAULT_TASK_TOKENS.items()}
    narrow = min(
        max_programs * max_professors_per_program,
        math.ceil(max_professors * RESEARCH_FACTOR),
    )
    tokens = (
        per_task["discover_programs"]
        + max_programs * per_task["research_professor"]
        + narrow * per_task["research_one_professor"]
    )

    left = None
    llm_kwargs = {}
    try:
        from api.providers import service as providers_service

        llm_kwargs = await providers_service.resolve_llm_kwargs(session, user_id, llm_provider)
    except Exception:  # noqa: BLE001 - an estimate never fails on provider lookup
        llm_kwargs = {}
    user = await session.get(User, user_id)
    cap, _ = billing.daily_ceilings(user)
    if cap > 0 and billing.uses_operator_key(llm_kwargs):
        left = max(cap - await billing.tokens_today(session, user_id), 0)
    return {
        "estimated_tokens": int(tokens),
        "narrow_tasks": narrow,
        "basis": "history" if averages else "defaults",
        "daily_allowance_left": left,
        "fits": None if left is None else tokens <= left,
    }
