from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.applicant_kit.routes import private_response
from api.auth.routes import get_current_user
from api.auth.schemas import UserOut
from api.autofill import schemas, service
from api.core.db import get_session
from api.core.ratelimit import rate_limit

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
