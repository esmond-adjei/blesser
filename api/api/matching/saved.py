"""Saved searches: a name, the catalogue filters, and how often to alert."""

from sqlalchemy import func, select

from api.core.exceptions import ConflictError, NotFoundError
from api.core.time import utcnow_naive
from api.matching import models as mm

MAX_PER_MEMBER = 20


def to_out(row: mm.SavedSearch) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "filters": row.filters or {},
        "alerts": row.alerts,
        "created_at": row.created_at,
    }


def clean_filters(filters: dict) -> dict:
    """Only set values, as plain JSON (enums by value)."""
    out = {}
    for key, value in filters.items():
        value = getattr(value, "value", value)
        if value not in (None, ""):
            out[key] = value
    return out


async def list_for(session, user_id: str) -> list[dict]:
    rows = (
        await session.execute(
            select(mm.SavedSearch)
            .where(mm.SavedSearch.user_id == user_id)
            .order_by(mm.SavedSearch.created_at.desc(), mm.SavedSearch.id)
        )
    ).scalars()
    return [to_out(r) for r in rows]


async def _own(session, user_id: str, search_id: str) -> mm.SavedSearch:
    row = await session.get(mm.SavedSearch, search_id)
    if row is None or row.user_id != user_id:
        raise NotFoundError("Saved search not found")
    return row


async def create(session, user_id: str, *, name: str, filters: dict, alerts: str) -> dict:
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"saved-search:{user_id}"))))
    count = await session.scalar(
        select(func.count()).select_from(mm.SavedSearch).where(mm.SavedSearch.user_id == user_id)
    )
    if (count or 0) >= MAX_PER_MEMBER:
        raise ConflictError(f"You can save up to {MAX_PER_MEMBER} searches. Delete one first.")
    row = mm.SavedSearch(
        user_id=user_id,
        name=name,
        filters=clean_filters(filters),
        alerts=alerts,
        # Alerts cover listings published from now on.
        last_alert_at=utcnow_naive(),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return to_out(row)


async def update(session, user_id: str, search_id: str, patch: dict) -> dict:
    row = await _own(session, user_id, search_id)
    if patch.get("name") is not None:
        row.name = patch["name"]
    if patch.get("alerts") is not None:
        if row.alerts == "off" and patch["alerts"] != "off":
            row.last_alert_at = utcnow_naive()
        row.alerts = patch["alerts"]
    await session.commit()
    await session.refresh(row)
    return to_out(row)


async def delete(session, user_id: str, search_id: str) -> None:
    row = await _own(session, user_id, search_id)
    await session.delete(row)
    await session.commit()
