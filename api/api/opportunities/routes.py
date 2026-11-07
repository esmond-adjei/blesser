"""Opportunity routes. Reads are public (no account needed); tracking and submitting
need a signed-in account; moderation needs an ops admin."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.applications import schemas as application_schemas
from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.core.db import get_session
from api.core.ratelimit import rate_limit
from api.core.time import utcnow_naive
from api.opportunities import schemas
from api.opportunities import service as opp_service
from api.opportunities.models import OpportunityCategory, OpportunityKind
from api.todos import ics

router = APIRouter(tags=["opportunities"])


@router.get("/opportunities", response_model=schemas.OpportunityPage)
async def list_opportunities(
    q: str = Query(default="", max_length=200),
    category: OpportunityCategory | None = None,
    kind: OpportunityKind | None = None,
    country: str | None = Query(default=None, max_length=80),
    include_closed: bool = False,
    closing_within: int | None = Query(default=None, ge=0, le=365),
    sort: Literal["deadline", "new"] = "deadline",
    limit: int = Query(default=30, ge=1, le=opp_service.MAX_PAGE),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """Public catalogue: published opportunities, open ones by default, soonest deadline first."""
    return await opp_service.list_public(
        session,
        q=q,
        category=category.value if category else None,
        kind=kind.value if kind else None,
        country=country,
        open_only=not include_closed,
        closing_within=closing_within,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/opportunities/facets", response_model=schemas.OpportunityFacets)
async def opportunity_facets(session: AsyncSession = Depends(get_session)):
    """Counts of open opportunities per category and kind."""
    return await opp_service.facets(session)


@router.get("/opportunities/tracked", response_model=dict[str, str])
async def tracked_opportunities(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """{opportunity_id: application_id} for everything you track."""
    return await opp_service.tracked_map(session, current.id)


@router.get("/opportunities/pending", response_model=list[schemas.OpportunityOut])
async def pending_opportunities(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Submissions waiting for review (ops admins only)."""
    return await opp_service.list_pending(session, current.id)


@router.post(
    "/opportunities",
    response_model=schemas.OpportunityOut,
    dependencies=[Depends(rate_limit("submit"))],
)
async def submit_opportunity(
    req: schemas.OpportunitySubmit,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Share an opportunity. It goes public once an ops admin publishes it."""
    return await opp_service.submit(session, current.id, req)


@router.get("/opportunities/{opportunity_id}", response_model=schemas.OpportunityOut)
async def get_opportunity(opportunity_id: str, session: AsyncSession = Depends(get_session)):
    return opp_service.to_out(await opp_service.get_or_404(session, opportunity_id))


@router.get("/opportunities/{opportunity_id}/calendar.ics", include_in_schema=False)
async def opportunity_ics(opportunity_id: str, session: AsyncSession = Depends(get_session)):
    """One all-day event on the deadline, to download or open in a calendar app."""
    opp = await opp_service.get_or_404(session, opportunity_id)
    events = []
    if opp.deadline_date is not None:
        events.append(
            ics.Event(
                uid=f"opportunity-{opp.id}@blesser",
                day=opp.deadline_date,
                summary=f"Deadline: {opp.title}"
                + (f" ({opp.organization})" if opp.organization else ""),
                description="\n\n".join(p for p in (opp.summary, opp.link or opp.source_url) if p),
                url=opp.link or opp.source_url,
                categories=[opp.category, opp_service.kind_label(opp.kind)],
            )
        )
    body = ics.render(events, name=opp.title, now=utcnow_naive())
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="opportunity-{opp.id}.ics"'},
    )


@router.post(
    "/opportunities/{opportunity_id}/track",
    response_model=application_schemas.ApplicationOut,
)
async def track_opportunity(
    opportunity_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Add the opportunity to your application tracker (idempotent): status,
    checklist, notes and deadline reminders then work as for any application."""
    app, _created = await opp_service.track(session, current.id, opportunity_id)
    return app


@router.patch("/opportunities/{opportunity_id}/status", response_model=schemas.OpportunityOut)
async def moderate_opportunity(
    opportunity_id: str,
    req: schemas.OpportunityModerate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Publish, hold or hide an opportunity (ops admins only)."""
    return await opp_service.moderate(session, current.id, opportunity_id, req.status.value)
