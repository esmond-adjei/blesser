"""Candidate routes: ranked shortlist, review records, review gate."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.candidates import schemas as candidate_schemas
from api.candidates import service as candidate_service
from api.core.db import get_session

router = APIRouter(tags=["candidates"])


@router.get(
    "/runs/{run_id}/candidates", response_model=list[candidate_schemas.CandidateOut]
)
async def list_candidates(
    run_id: str,
    response: Response,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="score"),
):
    """Every professor scored for this run, ranked; total in X-Total-Count."""
    items, total = await candidate_service.list_candidates(
        session, current.id, run_id, status=status, limit=limit, offset=offset, sort=sort
    )
    response.headers["X-Total-Count"] = str(total)
    return [candidate_schemas.CandidateOut(**d) for d in items]


@router.get(
    "/candidates/search", response_model=list[candidate_schemas.CandidateOut]
)
async def search_candidates(
    response: Response,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
    q: str | None = None,
    run_ids: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="score"),
):
    """Cross-run search by professor, school or program name; total in X-Total-Count."""
    ids = [r.strip() for r in (run_ids or "").split(",") if r.strip()] or None
    items, total = await candidate_service.search_candidates(
        session, current.id, q=q, run_ids=ids, status=status, limit=limit, offset=offset, sort=sort
    )
    response.headers["X-Total-Count"] = str(total)
    return [candidate_schemas.CandidateOut(**d) for d in items]


@router.get(
    "/candidates/{candidate_id}", response_model=candidate_schemas.CandidateDetailOut
)
async def get_candidate(
    candidate_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Full review record for one candidate."""
    return candidate_schemas.CandidateDetailOut(
        **await candidate_service.get_candidate_detail(session, current.id, candidate_id)
    )


@router.delete("/candidates/{candidate_id}")
async def delete_candidate(
    candidate_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Discard a candidate and its draft; papers stay with the professor."""
    return await candidate_service.delete_candidate(session, current.id, candidate_id)


@router.post("/candidates/{candidate_id}/review")
async def review_candidate(
    candidate_id: str,
    req: candidate_schemas.ApproveDraftRequest,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Approve or reject a candidate's draft; it is never sent from here."""
    return await candidate_service.review_candidate(
        session, current.id, candidate_id, req.approved
    )


@router.post("/runs/{run_id}/review-bulk")
async def review_bulk(
    run_id: str,
    req: candidate_schemas.BulkReviewRequest,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Approve/reject many candidates at once; never sends anything."""
    return await candidate_service.review_bulk(
        session, current.id, run_id, [r.model_dump() for r in req.reviews]
    )
