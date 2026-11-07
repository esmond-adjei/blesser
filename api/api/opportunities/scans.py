"""Scan runs: a run whose tasks are discover_opportunities, one per category.

People start scans from the Opportunities page; the worker can also start a
scheduled sweep (OPPORTUNITY_SWEEP_EMAIL + OPPORTUNITY_SWEEP_HOURS) so the
public catalogue stays fresh without anyone asking.
"""

from sqlalchemy import func, select

from api.auth import models as auth_models
from api.core.config import settings
from api.opportunities.models import OpportunityCategory
from api.opportunities.tasks import TASK_TYPE
from api.runs import models as run_models

#: Runs with this field are opportunity scans (the run list shows it).
SCAN_FIELD = "Opportunities"


def scan_field(categories: list[str]) -> str:
    return f"{SCAN_FIELD}: " + ", ".join(categories)


async def start_scan(
    session,
    user_id: str,
    *,
    categories: list[str],
    region: str = "",
    focus: str = "",
):
    """Create the run and queue one discovery task per category. Commits."""
    from api.runs import service as run_service

    ordered = [c.value for c in OpportunityCategory if c.value in set(categories)]
    if not ordered:
        ordered = [c.value for c in OpportunityCategory]
    region = region.strip() or settings.opportunity_default_region
    run = await run_service.create_run(
        session,
        user_id,
        region=region,
        field=scan_field(ordered),
        degree_level="either",
        interest_statement=focus.strip() or "-",
        initial_tasks=[{"task_type": TASK_TYPE, "target_name": f"category:{c}"} for c in ordered],
    )
    return run, len(ordered)


async def sweep_user_id(session) -> str | None:
    email = settings.opportunity_sweep_email.strip().lower()
    if not email or settings.opportunity_sweep_hours <= 0:
        return None
    return (
        await session.execute(
            select(auth_models.User.id).where(func.lower(auth_models.User.email) == email)
        )
    ).scalar_one_or_none()


async def maybe_sweep(session) -> str | None:
    """Start a scheduled scan when the last one is older than the sweep interval.

    Returns the new run id, or None. Safe to call often: it checks the newest
    scan run's age first.
    """
    user_id = await sweep_user_id(session)
    if user_id is None:
        return None
    # Aged in SQL: created_at is the DB's now(), which may not be UTC.
    age_seconds = (
        await session.execute(
            select(
                func.extract("epoch", func.localtimestamp() - func.max(run_models.Run.created_at))
            ).where(
                run_models.Run.user_id == user_id,
                run_models.Run.field.like(f"{SCAN_FIELD}:%"),
            )
        )
    ).scalar()
    if age_seconds is not None and float(age_seconds) < settings.opportunity_sweep_hours * 3600:
        return None
    run, _ = await start_scan(session, user_id, categories=[c.value for c in OpportunityCategory])
    return run.id
