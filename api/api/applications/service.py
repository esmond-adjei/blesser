"""Application tracker storage."""

from sqlalchemy import select

from api.applications import models as m
from api.applications import schemas
from api.applications.dates import parse_deadline
from api.core.exceptions import NotFoundError


def to_out(app: m.Application) -> dict:
    return {
        "id": app.id,
        "title": app.title,
        "organization": app.organization,
        "kind": app.kind,
        "location": app.location,
        "link": app.link,
        "benefits": app.benefits,
        "requirements": app.requirements or [],
        "deadline": app.deadline,
        "deadline_date": app.deadline_date,
        "status": app.status,
        "notes": app.notes,
        "opportunity_id": app.opportunity_id,
        "created_at": app.created_at,
        "updated_at": app.updated_at,
    }


async def list_applications(session, user_id: str) -> list[dict]:
    """Soonest deadline first; undated last."""
    rows = await session.execute(
        select(m.Application)
        .where(m.Application.user_id == user_id)
        .order_by(m.Application.deadline_date.asc().nulls_last(), m.Application.created_at.asc())
    )
    return [to_out(a) for a in rows.scalars()]


async def get_or_404(session, user_id: str, application_id: str) -> m.Application:
    app = await session.get(m.Application, application_id)
    if app is None or app.user_id != user_id:
        raise NotFoundError("Application not found")
    return app


async def create_application(session, user_id: str, data: schemas.ApplicationCreate) -> dict:
    fields = data.model_dump()
    fields["requirements"] = [r.model_dump() for r in data.requirements]
    fields["status"] = data.status.value
    fields["deadline_date"] = data.deadline_date or parse_deadline(data.deadline)
    app = m.Application(user_id=user_id, **fields)
    session.add(app)
    await session.commit()
    await session.refresh(app)
    return to_out(app)


async def update_application(
    session, user_id: str, application_id: str, data: schemas.ApplicationUpdate
) -> dict:
    app = await get_or_404(session, user_id, application_id)
    patch = data.model_dump(exclude_unset=True, mode="json")
    patch.pop("deadline_date", None)  # kept as a date, not the JSON-mode string
    for field, value in patch.items():
        if value is not None:
            setattr(app, field, value)
    if "deadline_date" in data.model_fields_set:
        app.deadline_date = data.deadline_date
    elif "deadline" in patch:
        app.deadline_date = parse_deadline(app.deadline)
    await session.commit()
    await session.refresh(app)
    return to_out(app)


async def delete_application(session, user_id: str, application_id: str) -> dict:
    app = await get_or_404(session, user_id, application_id)
    await session.delete(app)
    await session.commit()
    return {"status": "deleted"}
