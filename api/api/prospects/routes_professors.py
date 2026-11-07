"""Professor routes: manual professor management and narrow research queueing."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.core.db import get_session
from api.core.ratelimit import rate_limit
from api.prospects import schemas as prospect_schemas
from api.prospects import service as prospect_service
from api.runs import schemas as run_schemas

router = APIRouter(tags=["professors"])


@router.post(
    "/programs/{program_id}/professors",
    dependencies=[Depends(rate_limit("agent_work"))],
    response_model=prospect_schemas.ProfessorDetailOut,
)
async def create_professor(
    program_id: str,
    req: prospect_schemas.ProfessorCreate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Manually add a professor; queued for narrow research like a spawned name."""
    return prospect_schemas.ProfessorDetailOut(
        **await prospect_service.create_professor(
            session,
            current.id,
            program_id,
            name=req.name,
            profile_url=req.profile_url,
            email=req.email,
            openalex_id=req.openalex_id,
        )
    )


@router.get("/professors", response_model=list[run_schemas.RunFacultyOut])
async def list_professors(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Every professor the account has, each with their best match."""
    return [
        run_schemas.RunFacultyOut(**row)
        for row in await prospect_service.list_professors(session, current.id)
    ]


@router.post(
    "/professors/{professor_id}/match",
    response_model=prospect_schemas.ProfessorMatchOut,
    dependencies=[Depends(rate_limit("agent_work"))],
)
async def match_professor(
    professor_id: str,
    req: prospect_schemas.ProfessorMatchIn,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Score a professor against a run's or document's interests; `save` keeps it."""
    return prospect_schemas.ProfessorMatchOut(
        **await prospect_service.match_professor(
            session, current.id, professor_id,
            run_id=req.run_id, document_id=req.document_id, save=req.save,
        )
    )


@router.get(
    "/professors/{professor_id}", response_model=prospect_schemas.ProfessorDetailOut
)
async def get_professor(
    professor_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return prospect_schemas.ProfessorDetailOut(
        **await prospect_service.get_professor(session, current.id, professor_id)
    )


@router.patch(
    "/professors/{professor_id}", response_model=prospect_schemas.ProfessorDetailOut
)
async def update_professor(
    professor_id: str,
    req: prospect_schemas.ProfessorUpdate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return prospect_schemas.ProfessorDetailOut(
        **await prospect_service.update_professor(
            session, current.id, professor_id, req.model_dump(exclude_unset=True)
        )
    )


@router.delete("/professors/{professor_id}")
async def delete_professor(
    professor_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Delete a professor and their papers; 409 when a candidate exists."""
    return await prospect_service.delete_professor(session, current.id, professor_id)
