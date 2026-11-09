from sqlalchemy import func, select, update

from api.core.time import utcnow_naive
from api.editorial.models import SiteSetting
from api.editorial.service import get_settings
from api.opportunities.models import Opportunity


async def auto_archive(session):
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext("daily-auto-archive")))
    )
    settings = await get_settings(session)
    today = utcnow_naive().date()
    last = await session.get(SiteSetting, "last_archive_on")
    if not settings["auto_archive"] or (last and last.value == today.isoformat()):
        await session.commit()
        return 0
    result = await session.execute(
        update(Opportunity)
        .where(
            Opportunity.status == "published",
            Opportunity.rolling.is_(False),
            Opportunity.deadline_date < today,
        )
        .values(status="archived", updated_at=utcnow_naive())
    )
    if last:
        last.value = today.isoformat()
    else:
        session.add(SiteSetting(key="last_archive_on", value=today.isoformat()))
    await session.commit()
    return result.rowcount
