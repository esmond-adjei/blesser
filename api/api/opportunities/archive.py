from datetime import timedelta

from sqlalchemy import func, or_, select, update

from api.core.time import utcnow_naive
from api.editorial.models import SiteSetting
from api.editorial.service import get_settings
from api.opportunities.models import Opportunity


async def auto_archive(session):
    """Once per UTC date: archive passed deadlines, and undated listings gone stale.

    An undated or rolling listing counts as open only while something confirms it: the
    scheduled checks (freshness.py) re-read it every `recheck_days`, so one that nothing
    has confirmed for `stale_days` is archived. A new cycle can still reopen it.
    """
    from api.opportunities.freshness import config

    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext("daily-auto-archive")))
    )
    settings = await get_settings(session)
    now = utcnow_naive()
    today = now.date()
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
        .values(status="archived", updated_at=now)
    )
    stale_days = config(settings)["stale_days"]
    stale = await session.execute(
        update(Opportunity)
        .where(
            Opportunity.status == "published",
            or_(Opportunity.deadline_date.is_(None), Opportunity.rolling.is_(True)),
            func.coalesce(Opportunity.verified_at, Opportunity.created_at)
            < now - timedelta(days=stale_days),
        )
        .values(status="archived", check_outcome="stale", updated_at=now)
    )
    if last:
        last.value = today.isoformat()
    else:
        session.add(SiteSetting(key="last_archive_on", value=today.isoformat()))
    await session.commit()
    return result.rowcount + stale.rowcount
