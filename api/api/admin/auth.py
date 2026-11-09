from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import security, service
from api.auth.models import User
from api.core.db import get_session
from api.core.exceptions import AuthError, ForbiddenError

_bearer = HTTPBearer(auto_error=False)


async def get_staff(
    session: AsyncSession = Depends(get_session),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    user_id = (
        security.parse_access_token(credentials.credentials, "admin")
        if credentials
        else None
    )
    if user_id is None:
        raise AuthError("Staff sign in required.")
    user = await service.get_user_or_401(session, user_id)
    service.check_account(user, "admin")
    return user


async def get_admin(staff: User = Depends(get_staff)) -> User:
    if staff.role != "admin":
        raise ForbiddenError("Admin access required.")
    return staff
