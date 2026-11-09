from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.db import get_session
from api.core.exceptions import NotFoundError
from api.core.ratelimit import enforce
from api.editorial import models as m
from api.editorial import service as editorial
from api.opportunities import service, share
from api.opportunities.models import Opportunity, OpportunityCategory, OpportunityKind
from api.opportunities.schemas import OpportunityFacets
from api.public import schemas
from api.todos import ics

CACHE_CONTROL = "public, max-age=60, s-maxage=300, stale-while-revalidate=3600"


async def cache(request: Request, response: Response):
    if request.method == "GET":
        response.headers["Cache-Control"] = CACHE_CONTROL


router = APIRouter(tags=["public"], dependencies=[Depends(cache)])


async def by_slug(session, slug):
    row = (
        await session.execute(select(Opportunity).where(Opportunity.slug == slug))
    ).scalar_one_or_none()
    old = await session.get(m.SlugHistory, slug) if row is None else None
    if old:
        row = await session.get(Opportunity, old.opportunity_id)
    if (
        row is None
        or row.audience != "public"
        or row.status not in ("published", "archived")
    ):
        raise NotFoundError("Opportunity not found")
    return row


def redirect(row, slug, suffix=""):
    if row.slug != slug:
        return RedirectResponse(
            f"/api/public/opportunities/{quote(row.slug)}{suffix}",
            status_code=301,
            headers={"Cache-Control": CACHE_CONTROL},
        )


@router.get("/opportunities", response_model=schemas.PublicPage)
async def opportunities(
    q: str = Query("", max_length=200),
    category: OpportunityCategory | None = None,
    kind: OpportunityKind | None = None,
    country: str | None = Query(None, max_length=80),
    closing_within: int | None = Query(None, ge=0, le=365),
    include_closed: bool = False,
    sort: Literal["deadline", "new"] = "deadline",
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    return await service.list_public(
        session,
        public_only=True,
        q=q,
        category=category,
        kind=kind,
        country=country,
        closing_within=closing_within,
        open_only=not include_closed,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/facets", response_model=OpportunityFacets)
async def facets(session: AsyncSession = Depends(get_session)):
    return await service.facets(session, public_only=True)


@router.get("/opportunities/{slug}", response_model=schemas.PublicOpportunity)
async def opportunity(slug: str, session: AsyncSession = Depends(get_session)):
    row = await by_slug(session, slug)
    return redirect(row, slug) or service.to_out(row)


@router.get("/opportunities/{slug}/calendar.ics")
async def calendar(slug: str, session: AsyncSession = Depends(get_session)):
    row = await by_slug(session, slug)
    if response := redirect(row, slug, "/calendar.ics"):
        return response
    events = []
    if row.deadline_date:
        events.append(
            ics.Event(
                uid=f"opportunity-{row.id}@blesser",
                day=row.deadline_date,
                summary=f"Deadline: {row.title}",
                description=row.summary,
                url=row.link or row.source_url,
            )
        )
    return Response(
        ics.render(events, name=row.title, now=service.utcnow_naive()),
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": CACHE_CONTROL},
    )


@router.get("/opportunities/{slug}/share", response_model=share.ShareKit)
async def share_kit(slug: str, session: AsyncSession = Depends(get_session)):
    row = await by_slug(session, slug)
    if response := redirect(row, slug, "/share"):
        return response
    if row.status != "published":
        raise NotFoundError("Opportunity not found")
    return share.kit(row, None)


@router.get("/shared/{token}", response_model=share.SharedTeaser)
async def shared(token: str, session: AsyncSession = Depends(get_session)):
    """What a share link may show: members-only rows too, but never their official link."""
    ids = share.read_token(token)
    row = await session.get(Opportunity, ids[0]) if ids else None
    if row is None or row.status not in share.SHAREABLE:
        raise NotFoundError("Shared opportunity not found")
    return share.teaser(row)


@router.post("/submissions", status_code=201)
async def submit(
    req: schemas.Submission,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    response.headers["Cache-Control"] = "no-store"
    enforce("public_submit", request.client.host if request.client else "unknown")
    row = await service.submit(session, None, req)
    return {"id": row["id"]}


@router.post("/opportunities/{slug}/report", status_code=202)
async def report(
    slug: str,
    req: schemas.ReportIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    response.headers["Cache-Control"] = "no-store"
    enforce("public_report", request.client.host if request.client else "unknown")
    row = await by_slug(session, slug)
    session.add(
        m.OpportunityReport(opportunity_id=row.id, reason=req.reason, email=req.email)
    )
    row.review_reason = "reported"
    await session.commit()
    return {"status": "accepted"}


@router.get("/collections", response_model=list[schemas.PublicCollection])
async def collections(session: AsyncSession = Depends(get_session)):
    rows = (
        (
            await session.execute(
                select(m.Collection)
                .where(
                    m.Collection.published.is_(True), m.Collection.audience == "public"
                )
                .order_by(m.Collection.position, m.Collection.id)
            )
        )
        .scalars()
        .all()
    )
    return [
        await editorial.collection_out(session, row, public=True, limit=12)
        for row in rows
    ]


@router.get("/collections/{slug}", response_model=schemas.PublicCollection)
async def collection(slug: str, session: AsyncSession = Depends(get_session)):
    row = (
        await session.execute(
            select(m.Collection).where(
                m.Collection.slug == slug,
                m.Collection.published.is_(True),
                m.Collection.audience == "public",
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Collection not found")
    return await editorial.collection_out(session, row, public=True)


@router.get("/site", response_model=schemas.PublicSite)
async def site(session: AsyncSession = Depends(get_session)):
    rows = (
        (
            await session.execute(
                select(Opportunity)
                .where(
                    Opportunity.status == "published",
                    Opportunity.audience == "public",
                    Opportunity.featured_rank.is_not(None),
                )
                .order_by(Opportunity.featured_rank, Opportunity.id)
            )
        )
        .scalars()
        .all()
    )
    closing = await service.list_public(
        session, public_only=True, closing_within=14, limit=12
    )
    return {
        "content": await editorial.content(session, active=True),
        "featured": [service.to_out(r) for r in rows],
        "closing_soon": closing["items"],
    }


@router.get("/sitemap")
async def sitemap(session: AsyncSession = Depends(get_session)):
    rows = (
        (
            await session.execute(
                select(Opportunity)
                .where(
                    Opportunity.status == "published", Opportunity.audience == "public"
                )
                .order_by(Opportunity.slug)
            )
        )
        .scalars()
        .all()
    )
    collections = (
        (
            await session.execute(
                select(m.Collection.slug)
                .where(
                    m.Collection.published.is_(True), m.Collection.audience == "public"
                )
                .order_by(m.Collection.slug)
            )
        )
        .scalars()
        .all()
    )
    return {
        "opportunities": [
            {"slug": r.slug, "updated_at": r.updated_at.isoformat() + "Z"} for r in rows
        ],
        "collections": [{"slug": s} for s in collections],
    }
