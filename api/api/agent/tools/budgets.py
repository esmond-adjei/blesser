"""Per-task save budgets; run-level caps live in api/runs/budgets.py."""

from api.core.config import settings

TASK_COUNTER = {
    "programs": "programs_saved",
    "professors": "professors_saved",
    "drafts": "drafts_saved",
}

TASK_LIMIT = {
    "programs": "max_programs_per_task",
    "professors": "max_professors_per_task",
    "drafts": "max_drafts_per_task",
}


def check_task_budget(ctx, kind: str) -> dict | None:
    """Refusal once this task saved enough of `kind`, else None.

    Handlers increment only after a successful save, so deduped retries never consume budget.
    """
    counter_attr = TASK_COUNTER[kind]
    limit_attr = TASK_LIMIT[kind]
    count = getattr(ctx, counter_attr)
    limit = getattr(settings, limit_attr)
    if count < limit:
        return None
    return {
        "error": (
            f"Budget reached: at most {limit} {kind} may be saved per task "
            f"({count} already saved). Do not save more {kind}; write your "
            "final summary of what you found instead."
        )
    }
