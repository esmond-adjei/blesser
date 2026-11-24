from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.core.db import get_session
from api.matching import saved, schemas
from api.matching import service as matching

router = APIRouter(tags=["matching"], dependencies=[Depends(get_current_user)])


@router.get("/match-profile", response_model=schemas.MatchProfileOut)
async def get_match_profile(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Your feed settings. Before you save one, a suggestion from your Applicant Kit."""
    return await matching.read(session, current.id)


@router.put("/match-profile", response_model=schemas.MatchProfileOut)
async def put_match_profile(
    req: schemas.MatchProfileIn,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await matching.save(session, current.id, req.model_dump(mode="json"))


@router.delete("/match-profile", status_code=204)
async def delete_match_profile(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Forget the profile: "For you" falls back to deadline order and alerts stop."""
    await matching.delete(session, current.id)
    return Response(status_code=204)


@router.get("/saved-searches", response_model=list[schemas.SavedSearchOut])
async def list_saved_searches(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await saved.list_for(session, current.id)


@router.post("/saved-searches", response_model=schemas.SavedSearchOut, status_code=201)
async def create_saved_search(
    req: schemas.SavedSearchIn,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await saved.create(
        session,
        current.id,
        name=req.name,
        filters=req.filters.model_dump(mode="json"),
        alerts=req.alerts,
    )


@router.patch("/saved-searches/{search_id}", response_model=schemas.SavedSearchOut)
async def update_saved_search(
    search_id: str,
    req: schemas.SavedSearchPatch,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await saved.update(session, current.id, search_id, req.model_dump(exclude_unset=True))


@router.delete("/saved-searches/{search_id}", status_code=204)
async def delete_saved_search(
    search_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    await saved.delete(session, current.id, search_id)
    return Response(status_code=204)
