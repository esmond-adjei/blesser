"""The scheduled scans account: OPPORTUNITY_SWEEP_EMAIL.

Staff scan schedules (the catalogue sweep among them) and listing checks run as this
account; see api/scans/schedules.py. Without it they run as the first active admin.
"""

from sqlalchemy import func, select

from api.auth import models as auth_models
from api.core.config import settings


async def sweep_user_id(session) -> str | None:
    email = settings.opportunity_sweep_email.strip().lower()
    if not email:
        return None
    return (
        await session.execute(
            select(auth_models.User.id).where(
                func.lower(auth_models.User.email) == email,
                auth_models.User.disabled_at.is_(None),
            )
        )
    ).scalar_one_or_none()
