"""To-do routes and the calendar feed (the .ics route is public: its token is the key)."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.core.db import get_session
from api.core.exceptions import NotFoundError
from api.todos import schemas
from api.todos import service as todo_service

router = APIRouter(tags=["todos"])

ICS_TYPE = "text/calendar; charset=utf-8"


@router.get("/todos", response_model=list[schemas.TodoOut])
async def list_todos(
    status: Literal["open", "done", "all"] = Query(default="open"),
    opportunity_id: str | None = None,
    application_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Your to-dos: open ones by due date, undated last."""
    return await todo_service.list_todos(
        session,
        current.id,
        status=status,
        opportunity_id=opportunity_id,
        application_id=application_id,
    )


@router.post("/todos", response_model=schemas.TodoOut)
async def create_todo(
    req: schemas.TodoCreate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await todo_service.create_todo(session, current.id, req)


@router.patch("/todos/{todo_id}", response_model=schemas.TodoOut)
async def update_todo(
    todo_id: str,
    req: schemas.TodoUpdate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await todo_service.update_todo(session, current.id, todo_id, req)


@router.delete("/todos/{todo_id}")
async def delete_todo(
    todo_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await todo_service.delete_todo(session, current.id, todo_id)


@router.get("/calendar/feed", response_model=schemas.CalendarFeedOut)
async def get_feed(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Your private subscription URL (created on first request)."""
    return await todo_service.get_or_create_feed(session, current.id)


@router.post("/calendar/feed/rotate", response_model=schemas.CalendarFeedOut)
async def rotate_feed(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Replace the subscription URL; calendars using the old one stop updating."""
    return await todo_service.rotate_feed(session, current.id)


@router.get("/calendar/feed/{token}.ics", include_in_schema=False)
async def feed_ics(token: str, session: AsyncSession = Depends(get_session)):
    user_id = await todo_service.feed_owner(session, token)
    if user_id is None:
        raise NotFoundError("Calendar feed not found")
    body = await todo_service.render_feed(session, user_id)
    return Response(
        content=body,
        media_type=ICS_TYPE,
        headers={"Cache-Control": "private, max-age=900"},
    )
