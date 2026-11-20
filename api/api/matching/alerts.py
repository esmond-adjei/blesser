"""New-match alerts, run hourly from the worker (scans/queue.py hourly_jobs).

- new_match: listings published since the member's last alert that fit their
  match profile (service.fit_clause), daily or weekly.
- closing_match: once a week, fitting listings that close within two weeks.
- saved_search: listings published since the last alert that match a saved search.

Each run makes at most one notification per member and kind (one per saved
search), listing up to MAX_ITEMS. Email and push follow the member's
notification settings; with email off for a kind, the daily digest carries it.
Nothing goes out before ALERT_HOUR in the member's timezone. Listings the member
already tracks are left out.
"""

from datetime import datetime, timedelta

from sqlalchemy import func, select

from api.applications.models import Application
from api.core.time import utcnow_naive
from api.matching import models as mm
from api.matching import service as matching
from api.notifications import models as notification_models
from api.notifications.service import local_now, notify
from api.opportunities import models as om
from api.opportunities import service as opp_service

ALERT_HOUR = 8
MAX_ITEMS = 10
#: A listing published longer ago than this is never "new", however long alerts were off.
MAX_LOOKBACK = timedelta(days=8)
CLOSING_DAYS = 14


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _due(alerts: str, last: datetime | None, now: datetime, prefs) -> bool:
    if alerts == "off":
        return False
    if last is None:
        return True
    last_local = local_now(prefs, last).date()
    today = local_now(prefs, now).date()
    return (today - last_local).days >= (7 if alerts == "weekly" else 1)


def _not_tracked(user_id: str):
    return ~om.Opportunity.id.in_(
        select(Application.opportunity_id).where(
            Application.user_id == user_id, Application.opportunity_id.is_not(None)
        )
    )


def _item(opp: om.Opportunity, on) -> dict:
    out = opp_service.to_out(opp, on)
    bits = [opp.organization] if opp.organization else []
    if opp.rolling:
        bits.append("Rolling")
    elif out["days_left"] is not None:
        bits.append("Closes today" if out["days_left"] == 0 else f"Closes in {_plural(out['days_left'], 'day', 'days')}")
    return {"title": opp.title, "body": ", ".join(bits), "link": f"/opportunities/{opp.id}"}


async def _matches(session, stmt, limit: int = MAX_ITEMS):
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await session.execute(stmt.limit(limit))).all()
    return total, [row[0] for row in rows]


def _window(last: datetime | None, now: datetime):
    since = max(last or now - MAX_LOOKBACK, now - MAX_LOOKBACK)
    o = om.Opportunity
    return (o.published_at > since, o.published_at <= now)


async def _new_matches(session, profile: mm.MatchProfile, prefs, now: datetime, local) -> bool:
    match = matching.prefs_of(profile)
    on = local.date()
    score, _terms = matching.score_columns(match)
    stmt = (
        select(om.Opportunity, score)
        .where(
            *opp_service.catalogue_filters(on),
            *_window(profile.last_alert_at, now),
            matching.fit_clause(match),
            _not_tracked(profile.user_id),
        )
        .order_by(score.desc(), om.Opportunity.deadline_date.asc().nulls_last(), om.Opportunity.id)
    )
    profile.last_alert_at = now
    if not match.can_alert:
        return False
    total, rows = await _matches(session, stmt)
    if not total:
        return False
    period = "this week" if profile.alerts == "weekly" else "today"
    return await notify(
        session,
        user_id=profile.user_id,
        kind="new_match",
        title=f"{_plural(total, 'new opportunity fits', 'new opportunities fit')} you",
        body=f"Added {period}: " + "; ".join(r.title for r in rows[:3]) + ("" if total <= 3 else f"; and {total - 3} more"),
        link="/opportunities?sort=for_you",
        dedupe_key=f"match:new:{on.isoformat()}",
        items=[_item(r, on) for r in rows],
    )


async def _closing_matches(session, profile: mm.MatchProfile, now: datetime, local) -> bool:
    match = matching.prefs_of(profile)
    on = local.date()
    if profile.last_closing_on is not None and (on - profile.last_closing_on).days < 7:
        return False
    profile.last_closing_on = on
    if not match.can_alert:
        return False
    score, _terms = matching.score_columns(match)
    stmt = (
        select(om.Opportunity, score)
        .where(
            *opp_service.catalogue_filters(on, closing_within=CLOSING_DAYS),
            matching.fit_clause(match),
            _not_tracked(profile.user_id),
        )
        .order_by(om.Opportunity.deadline_date.asc(), score.desc(), om.Opportunity.id)
    )
    total, rows = await _matches(session, stmt)
    if not total:
        return False
    return await notify(
        session,
        user_id=profile.user_id,
        kind="closing_match",
        title=f"{_plural(total, 'opportunity that fits you closes', 'opportunities that fit you close')} soon",
        body="These close within two weeks: " + "; ".join(r.title for r in rows[:3]) + ("" if total <= 3 else f"; and {total - 3} more"),
        link="/opportunities?sort=for_you&soon=1",
        dedupe_key=f"match:closing:{on.isoformat()}",
        items=[_item(r, on) for r in rows],
    )


async def _saved_search(session, search: mm.SavedSearch, now: datetime, local) -> bool:
    on = local.date()
    filters = dict(search.filters or {})
    stmt = (
        select(om.Opportunity)
        .where(
            *opp_service.catalogue_filters(
                on,
                q=filters.get("q") or "",
                category=filters.get("category"),
                kind=filters.get("kind"),
                country=filters.get("country"),
                closing_within=filters.get("closing_within"),
            ),
            *_window(search.last_alert_at, now),
            _not_tracked(search.user_id),
        )
        .order_by(om.Opportunity.deadline_date.asc().nulls_last(), om.Opportunity.id)
    )
    search.last_alert_at = now
    total, rows = await _matches(session, stmt)
    if not total:
        return False
    return await notify(
        session,
        user_id=search.user_id,
        kind="saved_search",
        title=f"{_plural(total, 'new result', 'new results')} for “{search.name}”"[:200],
        body="; ".join(r.title for r in rows[:3]) + ("" if total <= 3 else f"; and {total - 3} more"),
        link=f"/opportunities?saved={search.id}",
        entity_id=search.id,
        dedupe_key=f"saved:{search.id}:{on.isoformat()}",
        items=[_item(r, on) for r in rows],
    )


async def run(session, now: datetime | None = None) -> int:
    """One pass over every member with alerts on. Returns notifications created.
    Commits after each member so one failure never repeats the others' alerts."""
    now = now or utcnow_naive()
    prefs_model = notification_models.NotificationPreference
    created = 0

    profiles = (
        await session.execute(
            select(mm.MatchProfile, prefs_model)
            .outerjoin(prefs_model, prefs_model.user_id == mm.MatchProfile.user_id)
            .where((mm.MatchProfile.alerts != "off") | mm.MatchProfile.closing_soon.is_(True))
            .order_by(mm.MatchProfile.user_id)
        )
    ).all()
    for profile, prefs in profiles:
        local = local_now(prefs, now)
        if local.hour < ALERT_HOUR:
            continue
        if _due(profile.alerts, profile.last_alert_at, now, prefs):
            created += await _new_matches(session, profile, prefs, now, local)
        if profile.closing_soon:
            created += await _closing_matches(session, profile, now, local)
        await session.commit()

    searches = (
        await session.execute(
            select(mm.SavedSearch, prefs_model)
            .outerjoin(prefs_model, prefs_model.user_id == mm.SavedSearch.user_id)
            .where(mm.SavedSearch.alerts != "off")
            .order_by(mm.SavedSearch.user_id, mm.SavedSearch.id)
        )
    ).all()
    for search, prefs in searches:
        local = local_now(prefs, now)
        if local.hour < ALERT_HOUR or not _due(search.alerts, search.last_alert_at, now, prefs):
            continue
        created += await _saved_search(session, search, now, local)
        await session.commit()
    return created
