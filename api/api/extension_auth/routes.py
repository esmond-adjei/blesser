from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.applicant_kit.routes import private_response
from api.applicant_kit.service import projects
from api.auth.routes import get_current_user
from api.auth.schemas import UserOut
from api.core.config import settings
from api.core.db import get_session
from api.core.exceptions import AuthError
from api.core.ratelimit import enforce
from api.extension_auth import service

router = APIRouter(
    prefix="/extension", tags=["extension"], dependencies=[Depends(private_response)]
)
Session = Annotated[AsyncSession, Depends(get_session)]
Member = Annotated[UserOut, Depends(get_current_user)]


class ConnectIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)


class RefreshIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    refresh_token: str = Field(min_length=1, max_length=512)


class SessionOut(BaseModel):
    id: str
    name: str
    created_at: datetime
    last_used_at: datetime | None


class PairOut(BaseModel):
    access_token: str
    refresh_token: str


class ConnectedOut(PairOut):
    session: SessionOut


async def get_extension_user(request: Request, current: Member):
    if not getattr(request.state, "extension_session_id", None):
        raise AuthError("An extension token is required.")
    return current


Extension = Annotated[UserOut, Depends(get_extension_user)]


@router.post("/connect", response_model=ConnectedOut, status_code=201)
async def connect(req: ConnectIn, session: Session, current: Member):
    enforce("extension_connect", current.id)
    return await service.connect(session, current.id, req.name)


@router.post("/refresh", response_model=PairOut)
async def refresh(req: RefreshIn, request: Request, session: Session):
    enforce("extension_refresh", request.client.host if request.client else "unknown")
    return await service.refresh(session, req.refresh_token)


@router.get("/sessions", response_model=list[SessionOut])
async def sessions(session: Session, current: Member):
    return await service.sessions(session, current.id)


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke(session_id: str, session: Session, current: Member):
    await service.revoke_owned(session, current.id, session_id)


@router.post("/logout", status_code=204)
async def logout(
    req: RefreshIn, request: Request, session: Session, current: Extension
):
    await service.logout(
        session, current.id, request.state.extension_session_id, req.refresh_token
    )


@router.get("/me")
async def me(session: Session, current: Extension):
    from api.autofill.service import remaining_today

    return {
        "user": {
            "id": current.id,
            "email": current.email,
            "display_name": current.display_name,
        },
        "projects": [
            {k: project[k] for k in ("id", "name", "tagline")}
            for project in await projects(session, current.id)
        ],
        "drafting": {
            "enabled": settings.autofill_drafts_per_day > 0,
            "remaining_today": await remaining_today(session, current.id),
        },
    }
