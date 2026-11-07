"""Program routes: manual program management and faculty research queueing."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.core.db import get_session
from api.core.ratelimit import rate_limit
from api.prospects import schemas as prospect_schemas
from api.prospects import service as prospect_service

router = APIRouter(tags=["programs"])


@router.post(
    "/schools/{school_id}/programs",
    response_model=prospect_schemas.ProgramDetailOut,
    dependencies=[Depends(rate_limit("agent_work"))],
)
async def create_program(
    school_id: str,
    req: prospect_schemas.ProgramCreate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Manually add a program; queued for faculty research."""
    return prospect_schemas.ProgramDetailOut(
        **await prospect_service.create_program(
            session, current.id, school_id, name=req.name, department_url=req.department_url
        )
    )


@router.get("/programs/{program_id}", response_model=prospect_schemas.ProgramDetailOut)
async def get_program(
    program_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return prospect_schemas.ProgramDetailOut(
        **await prospect_service.get_program(session, current.id, program_id)
    )


@router.patch(
    "/programs/{program_id}", response_model=prospect_schemas.ProgramDetailOut
)
async def update_program(
    program_id: str,
    req: prospect_schemas.ProgramUpdate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return prospect_schemas.ProgramDetailOut(
        **await prospect_service.update_program(
            session, current.id, program_id, req.model_dump(exclude_unset=True)
        )
    )


@router.delete("/programs/{program_id}")
async def delete_program(
    program_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Delete a program and its undiscovered professors; same 409 rule as schools."""
    return await prospect_service.delete_program(session, current.id, program_id)
