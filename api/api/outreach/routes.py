"""Outreach routes: draft queueing, outbox, editing, discard."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.core.db import get_session
from api.core.ratelimit import rate_limit
from api.outreach import schemas as outreach_schemas
from api.outreach import service as outreach_service

router = APIRouter(tags=["outreach"])


@router.post("/candidates/{candidate_id}/request-draft", dependencies=[Depends(rate_limit("agent_work"))])
async def request_draft(
    candidate_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Queue email drafting for one candidate."""
    return await outreach_service.request_draft(session, current.id, candidate_id)


@router.post("/runs/{run_id}/request-drafts", dependencies=[Depends(rate_limit("agent_work"))])
async def request_drafts(
    run_id: str,
    req: outreach_schemas.BulkDraftRequest,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Queue drafting for many candidates; unknown or foreign ids are reported as skipped."""
    return await outreach_service.request_drafts(session, current.id, run_id, req.candidate_ids)


@router.get("/runs/{run_id}/drafts", response_model=list[outreach_schemas.DraftOut])
async def list_drafts(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Outbox view: every draft queued for this run, newest first."""
    return [
        outreach_schemas.DraftOut(**d)
        for d in await outreach_service.list_drafts(session, current.id, run_id)
    ]


@router.get(
    "/candidates/{candidate_id}/drafts",
    response_model=list[outreach_schemas.DraftOut],
)
async def list_candidate_drafts(
    candidate_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Dossier view: every draft saved for one candidate, newest first."""
    return [
        outreach_schemas.DraftOut(**d)
        for d in await outreach_service.list_candidate_drafts(session, current.id, candidate_id)
    ]


@router.patch("/drafts/{draft_id}", response_model=outreach_schemas.DraftOut)
async def update_draft(
    draft_id: str,
    req: outreach_schemas.DraftUpdate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Edit a draft in place (sending stays manual)."""
    return outreach_schemas.DraftOut(
        **await outreach_service.update_draft(
            session, current.id, draft_id, req.model_dump(exclude_unset=True)
        )
    )


@router.delete("/drafts/{draft_id}")
async def delete_draft(
    draft_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Discard a draft; a `drafted` candidate falls back to `scored`."""
    return await outreach_service.delete_draft(session, current.id, draft_id)
