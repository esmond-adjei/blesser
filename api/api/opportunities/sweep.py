"""Scheduled catalogue refresh: OPPORTUNITY_SWEEP_EMAIL + OPPORTUNITY_SWEEP_HOURS.

Once an hour the worker checks whether that account's newest scan is older than
the interval and, if so, scans every category in OPPORTUNITY_DEFAULT_REGION.
"""

from sqlalchemy import func, select

from api.auth import models as auth_models
from api.core.config import settings
from api.opportunities.models import OpportunityCategory
from api.scans import models as scan_models


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
    """Start a scheduled scan when the last one is old enough; returns its id, or None."""
    from api.scans.service import start_scan

    user_id = await sweep_user_id(session)
    if user_id is None:
        return None
    last = (
        await session.execute(
            select(func.max(scan_models.Scan.created_at)).where(scan_models.Scan.user_id == user_id)
        )
    ).scalar()
    if last is not None:
        from datetime import timedelta

        from api.core.time import utcnow_naive

        if utcnow_naive() - last < timedelta(hours=settings.opportunity_sweep_hours):
            return None
    scan = await start_scan(session, user_id, categories=[c.value for c in OpportunityCategory])
    return scan.id
