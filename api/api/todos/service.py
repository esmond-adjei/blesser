"""To-do storage and the private calendar feed.

The feed is one secret URL per account that any calendar app can subscribe to
(Google Calendar "From URL", Apple Calendar, Outlook). It lists the deadlines of
applications still being worked on and every open to-do with a due date.
"""

import secrets
from datetime import timedelta

from sqlalchemy import func, select

from api.applications import models as application_models
from api.auth.security import hash_token
from api.core.config import settings
from api.core.exceptions import BadRequestError, NotFoundError
from api.core.time import utcnow_naive
from api.notifications.deadlines import OPEN_STATUSES
from api.opportunities import models as opportunity_models
from api.todos import ics, schemas
from api.todos import models as m

#: Past items the feed keeps, so a calendar does not lose what just happened.
FEED_PAST_DAYS = 30


def _application_label(app: application_models.Application) -> str:
    return app.school + (f", {app.program}" if app.program else "")


async def _labels(session, rows: list[m.Todo]) -> tuple[dict[str, str], dict[str, str]]:
    opp_ids = {r.opportunity_id for r in rows if r.opportunity_id}
    app_ids = {r.application_id for r in rows if r.application_id}
    opps: dict[str, str] = {}
    apps: dict[str, str] = {}
    if opp_ids:
        result = await session.execute(
            select(opportunity_models.Opportunity.id, opportunity_models.Opportunity.title).where(
                opportunity_models.Opportunity.id.in_(opp_ids)
            )
        )
        opps = dict(result.all())
    if app_ids:
        result = await session.execute(
            select(application_models.Application).where(
                application_models.Application.id.in_(app_ids)
            )
        )
        apps = {a.id: _application_label(a) for a in result.scalars()}
    return opps, apps


def _to_out(row: m.Todo, opps: dict[str, str], apps: dict[str, str]) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "notes": row.notes,
        "due_date": row.due_date,
        "priority": row.priority,
        "done": row.done,
        "done_at": row.done_at,
        "position": row.position,
        "opportunity_id": row.opportunity_id,
        "application_id": row.application_id,
        "opportunity_title": opps.get(row.opportunity_id or ""),
        "application_label": apps.get(row.application_id or ""),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


async def _one_out(session, row: m.Todo) -> dict:
    opps, apps = await _labels(session, [row])
    return _to_out(row, opps, apps)


async def list_todos(
    session,
    user_id: str,
    *,
    status: str = "open",
    opportunity_id: str | None = None,
    application_id: str | None = None,
) -> list[dict]:
    """Open first by due date (undated last), then manual position."""
    stmt = select(m.Todo).where(m.Todo.user_id == user_id)
    if status == "open":
        stmt = stmt.where(m.Todo.done.is_(False))
    elif status == "done":
        stmt = stmt.where(m.Todo.done.is_(True))
    if opportunity_id:
        stmt = stmt.where(m.Todo.opportunity_id == opportunity_id)
    if application_id:
        stmt = stmt.where(m.Todo.application_id == application_id)
    stmt = stmt.order_by(
        m.Todo.done.asc(),
        m.Todo.due_date.asc().nulls_last(),
        m.Todo.position.asc(),
        m.Todo.created_at.asc(),
    )
    rows = list((await session.execute(stmt)).scalars())
    opps, apps = await _labels(session, rows)
    return [_to_out(r, opps, apps) for r in rows]


async def _get_or_404(session, user_id: str, todo_id: str) -> m.Todo:
    row = await session.get(m.Todo, todo_id)
    if row is None or row.user_id != user_id:
        raise NotFoundError("To-do not found")
    return row


async def _check_links(session, user_id: str, opportunity_id, application_id) -> None:
    if opportunity_id:
        opp = await session.get(opportunity_models.Opportunity, opportunity_id)
        if opp is None:
            raise BadRequestError("Opportunity not found")
    if application_id:
        app = await session.get(application_models.Application, application_id)
        if app is None or app.user_id != user_id:
            raise BadRequestError("Application not found")


async def create_todo(session, user_id: str, data: schemas.TodoCreate) -> dict:
    await _check_links(session, user_id, data.opportunity_id, data.application_id)
    last = (
        await session.execute(
            select(func.max(m.Todo.position)).where(m.Todo.user_id == user_id)
        )
    ).scalar()
    row = m.Todo(
        user_id=user_id,
        title=data.title.strip(),
        notes=data.notes,
        due_date=data.due_date,
        priority=data.priority.value,
        opportunity_id=data.opportunity_id,
        application_id=data.application_id,
        position=(last or 0) + 1,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return await _one_out(session, row)


async def update_todo(session, user_id: str, todo_id: str, data: schemas.TodoUpdate) -> dict:
    row = await _get_or_404(session, user_id, todo_id)
    patch = data.model_dump(exclude_unset=True)
    if "title" in patch and patch["title"] is not None:
        row.title = patch["title"].strip()
    if "notes" in patch and patch["notes"] is not None:
        row.notes = patch["notes"]
    if "due_date" in patch:
        row.due_date = patch["due_date"]
    if patch.get("priority") is not None:
        row.priority = patch["priority"].value
    if patch.get("position") is not None:
        row.position = patch["position"]
    if patch.get("done") is not None and patch["done"] != row.done:
        row.done = patch["done"]
        row.done_at = utcnow_naive() if row.done else None
    await session.commit()
    await session.refresh(row)
    return await _one_out(session, row)


async def delete_todo(session, user_id: str, todo_id: str) -> dict:
    row = await _get_or_404(session, user_id, todo_id)
    await session.delete(row)
    await session.commit()
    return {"status": "deleted"}


# --- Calendar feed ---------------------------------------------------------


def _api_base() -> str:
    return (settings.public_api_url or settings.app_base_url).rstrip("/")


def feed_url(token: str) -> str:
    return f"{_api_base()}/api/calendar/feed/{token}.ics"


def _feed_out(feed: m.CalendarFeed) -> dict:
    url = feed_url(feed.token)
    webcal = "webcal://" + url.split("://", 1)[-1]
    return {"url": url, "webcal_url": webcal, "created_at": feed.created_at}


async def get_or_create_feed(session, user_id: str) -> dict:
    feed = await session.get(m.CalendarFeed, user_id)
    if feed is None:
        token = secrets.token_urlsafe(24)
        feed = m.CalendarFeed(user_id=user_id, token=token, token_hash=hash_token(token))
        session.add(feed)
        await session.commit()
        await session.refresh(feed)
    return _feed_out(feed)


async def rotate_feed(session, user_id: str) -> dict:
    """A new secret URL; the old one stops working at once."""
    feed = await session.get(m.CalendarFeed, user_id)
    token = secrets.token_urlsafe(24)
    if feed is None:
        feed = m.CalendarFeed(user_id=user_id)
        session.add(feed)
    feed.token = token
    feed.token_hash = hash_token(token)
    feed.created_at = utcnow_naive()
    await session.commit()
    await session.refresh(feed)
    return _feed_out(feed)


async def feed_owner(session, token: str) -> str | None:
    return (
        await session.execute(
            select(m.CalendarFeed.user_id).where(m.CalendarFeed.token_hash == hash_token(token))
        )
    ).scalar_one_or_none()


def _app_link(path: str) -> str:
    return f"{settings.app_base_url.rstrip('/')}{path}"


async def feed_events(session, user_id: str) -> list[ics.Event]:
    since = utcnow_naive().date() - timedelta(days=FEED_PAST_DAYS)
    app_model = application_models.Application
    apps = (
        await session.execute(
            select(app_model).where(
                app_model.user_id == user_id,
                app_model.deadline_date.is_not(None),
                app_model.deadline_date >= since,
                app_model.status.in_(OPEN_STATUSES),
            )
        )
    ).scalars()
    events: list[ics.Event] = []
    for app in apps:
        assert app.deadline_date is not None
        label = _application_label(app)
        events.append(
            ics.Event(
                uid=f"application-{app.id}@blesser",
                day=app.deadline_date,
                summary=f"Deadline: {label}",
                description="\n".join(
                    part
                    for part in (
                        f"Status: {app.status}",
                        app.link,
                        _app_link(f"/applications/{app.id}"),
                    )
                    if part
                ),
                url=app.link or _app_link(f"/applications/{app.id}"),
                categories=["Deadline"],
            )
        )
    todos = (
        await session.execute(
            select(m.Todo).where(
                m.Todo.user_id == user_id,
                m.Todo.done.is_(False),
                m.Todo.due_date.is_not(None),
                m.Todo.due_date >= since,
            )
        )
    ).scalars()
    for todo in todos:
        assert todo.due_date is not None
        events.append(
            ics.Event(
                uid=f"todo-{todo.id}@blesser",
                day=todo.due_date,
                summary=f"To-do: {todo.title}",
                description=todo.notes,
                url=_app_link("/todos"),
                categories=["To-do"],
                alarm_days=(1,),
            )
        )
    events.sort(key=lambda e: (e.day, e.summary))
    return events


async def render_feed(session, user_id: str) -> str:
    events = await feed_events(session, user_id)
    return ics.render(events, name="Blesser: deadlines and to-dos", now=utcnow_naive())
