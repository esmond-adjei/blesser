"""Usage views: your own consumption, and an ops view across accounts."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import schemas as auth_schemas
from api.auth import service as auth_service
from api.auth.routes import get_current_user
from api.core.config import settings
from api.core.db import get_session
from api.core.exceptions import ForbiddenError
from api.metering import service as metering

router = APIRouter(tags=["usage"])


@router.get("/usage")
async def my_usage(
    days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Your model calls and tokens per day and per feature/provider/model."""
    return await metering.summary(session, current.id, days)


@router.get("/ops/usage")
async def ops_usage(
    days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Cost/abuse view across accounts (OPS_ADMIN_EMAILS, only once verified:
    registration signs in before verification)."""
    admins = {
        e.strip().lower() for e in settings.ops_admin_emails.split(",") if e.strip()
    }
    user = await auth_service.get_user_or_401(session, current.id)
    if user.email.lower() not in admins or user.email_verified_at is None:
        raise ForbiddenError("Ops access only.")
    out = await metering.summary(session, None, days)
    out["top_accounts"] = await metering.top_accounts(session, days)
    return out
