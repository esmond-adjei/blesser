"""Application tracker routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.applications import schemas, service
from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.core.db import get_session

router = APIRouter(tags=["applications"])


@router.get("/applications", response_model=list[schemas.ApplicationOut])
async def list_applications(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await service.list_applications(session, current.id)


@router.get("/applications/{application_id}", response_model=schemas.ApplicationOut)
async def get_application(
    application_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return service.to_out(await service.get_or_404(session, current.id, application_id))


@router.post("/applications", response_model=schemas.ApplicationOut)
async def create_application(
    req: schemas.ApplicationCreate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Track something by hand (catalogue opportunities use /opportunities/{id}/track)."""
    return await service.create_application(session, current.id, req)


@router.patch("/applications/{application_id}", response_model=schemas.ApplicationOut)
async def update_application(
    application_id: str,
    req: schemas.ApplicationUpdate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await service.update_application(session, current.id, application_id, req)


@router.delete("/applications/{application_id}")
async def delete_application(
    application_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await service.delete_application(session, current.id, application_id)
