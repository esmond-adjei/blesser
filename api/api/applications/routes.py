"""Application routes: the grad-application tracker (manual + agent-indexed)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.applications import schemas as application_schemas
from api.applications import service as application_service
from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.core.db import get_session

router = APIRouter(tags=["applications"])


@router.get("/applications", response_model=list[application_schemas.ApplicationOut])
async def list_applications(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Every tracked application, oldest first (filtering is client-side)."""
    return [
        application_schemas.ApplicationOut(**d)
        for d in await application_service.list_applications(session, current.id)
    ]


@router.get(
    "/applications/{application_id}", response_model=application_schemas.ApplicationOut
)
async def get_application(
    application_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """One tracked application with its checklist, waiver, and notes."""
    app = await application_service.get_application_or_404(
        session, application_id, current.id
    )
    return application_schemas.ApplicationOut(**application_service.to_out(app))


@router.post("/applications", response_model=application_schemas.ApplicationOut)
async def create_application(
    req: application_schemas.ApplicationCreate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Track a new application by hand (agents use the save_application tool)."""
    return application_schemas.ApplicationOut(
        **await application_service.create_application(session, current.id, req)
    )


@router.patch(
    "/applications/{application_id}", response_model=application_schemas.ApplicationOut
)
async def update_application(
    application_id: str,
    req: application_schemas.ApplicationUpdate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Edit a tracked application; only provided fields are written."""
    return application_schemas.ApplicationOut(
        **await application_service.update_application(
            session, current.id, application_id, req
        )
    )


@router.delete("/applications/{application_id}")
async def delete_application(
    application_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Remove a tracked application."""
    return await application_service.delete_application(
        session, current.id, application_id
    )


@router.post(
    "/applications/{application_id}/resolve-professors",
    response_model=application_schemas.ApplicationOut,
)
async def resolve_professors(
    application_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Link bare professor names to researched professors and candidates; ambiguous
    names stay unresolved and researcher-set ids are never changed."""
    return application_schemas.ApplicationOut(
        **await application_service.resolve_professors(
            session, current.id, application_id
        )
    )
