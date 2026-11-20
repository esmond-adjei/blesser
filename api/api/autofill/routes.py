from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.applicant_kit.routes import private_response
from api.auth.routes import get_current_user
from api.auth.schemas import UserOut
from api.autofill import feedback, schemas, service
from api.core.db import get_session
from api.core.ratelimit import rate_limit
from api.extension_auth.routes import Extension

router = APIRouter(
    prefix="/autofill", tags=["autofill"], dependencies=[Depends(private_response)]
)


@router.post(
    "/fill",
    response_model=schemas.FillResponse,
    dependencies=[Depends(rate_limit("autofill"))],
)
async def fill(
    req: schemas.FillRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current: Annotated[UserOut, Depends(get_current_user)],
):
    return await service.fill(session, current.id, req)


@router.get(
    "/match",
    response_model=schemas.PageMatch,
    dependencies=[Depends(rate_limit("autofill_match"))],
)
async def match(
    session: Annotated[AsyncSession, Depends(get_session)],
    current: Annotated[UserOut, Depends(get_current_user)],
    url: Annotated[str, Query(max_length=2048)],
    title: Annotated[str, Query(max_length=500)] = "",
):
    """Which tracked application the page in the member's tab belongs to."""
    found = await service.match_application(session, current.id, url, title)
    return found or {"application_id": None, "opportunity_id": None}


@router.post(
    "/feedback", status_code=204, dependencies=[Depends(rate_limit("autofill"))]
)
async def remember(
    req: schemas.FillFeedback,
    session: Annotated[AsyncSession, Depends(get_session)],
    current: Extension,
):
    await feedback.remember(session, current.id, req)


@router.get("/corrections", response_model=list[schemas.Correction])
async def corrections(
    session: Annotated[AsyncSession, Depends(get_session)],
    current: Annotated[UserOut, Depends(get_current_user)],
):
    return await feedback.corrections(session, current.id)


@router.delete("/corrections/{correction_id}", status_code=204)
async def forget(
    correction_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    current: Annotated[UserOut, Depends(get_current_user)],
):
    await feedback.forget(session, current.id, correction_id)


@router.post(
    "/reports", status_code=204, dependencies=[Depends(rate_limit("autofill"))]
)
async def report(
    req: schemas.FormReport,
    session: Annotated[AsyncSession, Depends(get_session)],
    current: Extension,
):
    await feedback.report(session, current.id, req)
