"""Account data export routes.

Create requires a verified email. Downloads use a separate short-lived signed
link scoped to the owner and export, so the browser needs no Bearer header.
"""

from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.account import export as account_export
from api.account import models as account_models
from api.auth import email_flows
from api.auth import schemas as auth_schemas
from api.auth import security as auth_security
from api.auth import service as auth_service
from api.auth.routes import get_current_user
from api.billing import service as billing
from api.core.db import get_session
from api.core.exceptions import ConflictError, NotFoundError
from api.core.ratelimit import rate_limit
from api.core.time import utcnow_naive

router = APIRouter(tags=["account"])
LINK_TTL = timedelta(minutes=5)


def _out(row) -> dict:
    return {
        "id": row.id,
        "status": row.status,
        "size_bytes": row.size_bytes,
        "error": row.error,
        "created_at": row.created_at,
        "expires_at": row.expires_at,
    }


async def _sweep(session, user_id: str) -> None:
    """Drop expired archives (rows + files) for this account."""
    await account_export.sweep_expired_exports(session, user_id)


@router.get("/account/exports")
async def list_exports(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    await _sweep(session, current.id)
    rows = (
        (
            await session.execute(
                select(account_models.AccountExport)
                .where(account_models.AccountExport.user_id == current.id)
                .order_by(account_models.AccountExport.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_out(r) for r in rows]


@router.post("/account/exports", dependencies=[Depends(rate_limit("upload"))])
async def create_export(
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Start building an archive of your account (verified email required)."""
    user = await auth_service.get_user_or_401(session, current.id)
    email_flows.require_verified(user)
    await billing.require_feature(session, user.id, "data_export")
    await _sweep(session, user.id)
    running = (
        await session.execute(
            select(account_models.AccountExport.id).where(
                account_models.AccountExport.user_id == user.id,
                account_models.AccountExport.status == "pending",
            )
        )
    ).first()
    if running:
        raise ConflictError("An export is already being prepared.")
    row = account_models.AccountExport(
        user_id=user.id,
        status="pending",
        expires_at=utcnow_naive() + account_export.EXPORT_TTL,
    )
    session.add(row)
    await session.commit()
    background.add_task(account_export.build_archive, user.id, row.id)
    return _out(row)


@router.post("/account/exports/{export_id}/link")
async def export_link(
    export_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """A 5-minute download URL for one of your ready archives."""
    row = await session.get(account_models.AccountExport, export_id)
    if row is None or row.user_id != current.id or row.status != "ready":
        raise NotFoundError("Export not found")
    token = auth_security.signed_token(
        "export_dl", {"u": current.id, "x": row.id}, LINK_TTL
    )
    return {"url": f"/api/account/exports/{row.id}/file?t={token}"}


@router.get("/account/exports/{export_id}/file")
async def export_file(
    export_id: str, t: str, session: AsyncSession = Depends(get_session)
):
    claims = auth_security.read_signed("export_dl", t)
    row = await session.get(account_models.AccountExport, export_id)
    if (
        claims is None
        or row is None
        or claims.get("x") != row.id
        or claims.get("u") != row.user_id
        or row.status != "ready"
        or row.expires_at <= utcnow_naive()
    ):
        raise NotFoundError("This download link has expired. Create a new one.")
    path = account_export.archive_path(row.user_id, row.id)
    if not path.exists():
        raise NotFoundError("This download link has expired. Create a new one.")
    stamp = row.created_at.strftime("%Y-%m-%d")
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"graduator-export-{stamp}.zip",
        headers={"Cache-Control": "no-store"},
    )
