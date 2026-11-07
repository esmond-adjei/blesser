"""School routes: discovery tree and manual school management."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.core.db import get_session
from api.core.ratelimit import rate_limit
from api.prospects import schemas as prospect_schemas
from api.prospects import service as prospect_service
from api.prospects import tiers
from api.runs import schemas as run_schemas

router = APIRouter(tags=["schools"])

#: ?tier= on the account's schools: a tier key, or "none".
_TIER_PATTERN = "^(" + "|".join([*tiers.TIERS, "none"]) + ")$"


@router.get("/runs/{run_id}/programs", response_model=list[prospect_schemas.SchoolOut])
async def list_programs(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Discovery tree for a run: schools, programs and professor counts."""
    return [
        prospect_schemas.SchoolOut(**d)
        for d in await prospect_service.list_programs_tree(session, current.id, run_id)
    ]


@router.post("/runs/{run_id}/schools", response_model=prospect_schemas.SchoolOut, dependencies=[Depends(rate_limit("agent_work"))])
async def create_school(
    run_id: str,
    req: prospect_schemas.SchoolCreate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Manually add a school; inline programs each queue faculty research."""
    return prospect_schemas.SchoolOut(
        **await prospect_service.create_school(
            session,
            current.id,
            run_id,
            name=req.name,
            country=req.country,
            website_url=req.website_url,
            programs=req.programs,
        )
    )


@router.get("/schools", response_model=list[prospect_schemas.SchoolOut])
async def list_schools(
    tier: str | None = Query(None, pattern=_TIER_PATTERN),
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Every school the account has, with programmes and runs; `tier` filters ("none" = untiered)."""
    return [
        prospect_schemas.SchoolOut(**d)
        for d in await prospect_service.list_account_schools(session, current.id, tier)
    ]


@router.get("/schools/{school_id}/faculty", response_model=list[run_schemas.RunFacultyOut])
async def school_faculty(
    school_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """A school's faculty across every run, each with their best candidate."""
    return [
        run_schemas.RunFacultyOut(**row)
        for row in await prospect_service.school_faculty(session, current.id, school_id)
    ]


@router.get("/schools/{school_id}", response_model=prospect_schemas.SchoolOut)
async def get_school(
    school_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return prospect_schemas.SchoolOut(
        **await prospect_service.get_school(session, current.id, school_id)
    )


@router.patch("/schools/{school_id}", response_model=prospect_schemas.SchoolOut)
async def update_school(
    school_id: str,
    req: prospect_schemas.SchoolUpdate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return prospect_schemas.SchoolOut(
        **await prospect_service.update_school(
            session, current.id, school_id, req.model_dump(exclude_unset=True)
        )
    )


@router.delete("/schools/{school_id}")
async def delete_school(
    school_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Delete a school and its undiscovered subtree; 409 when any professor has a candidate."""
    return await prospect_service.delete_school(session, current.id, school_id)
