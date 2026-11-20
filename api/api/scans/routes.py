"""Scan routes: start agent scans for opportunities and watch them work."""

from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.core.config import settings
from api.core.db import get_session
from api.core.ratelimit import enforce_scan_limit
from api.opportunities.models import OpportunityCategory
from api.scans import service, sources

router = APIRouter(tags=["scans"])


class ScanCreate(BaseModel):
    # One audience per scan keeps each agent's search precise.
    categories: list[OpportunityCategory] = Field(min_length=1, max_length=1)
    region: str = Field(default="", max_length=120)
    focus: str = Field(
        default="",
        max_length=2000,
        description="Optional: sectors, fields or kinds to look for first.",
    )
    sites: list[Annotated[str, Field(max_length=2000)]] = Field(
        default_factory=list,
        max_length=service.MAX_SCAN_SITES,
        description="Optional: up to five public sites to read before searching.",
    )


class TaskOut(BaseModel):
    metrics: dict = Field(default_factory=dict)
    id: str
    task_type: str
    target: str | None
    status: str
    error: str | None
    final_text: str | None
    turns: int | None
    log: list[dict]
    input_tokens: int | None
    output_tokens: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ScanFindOut(BaseModel):
    opportunity_id: str
    title: str
    slug: str | None = None
    category: str | None = None
    kind: str | None = None
    deadline_date: date | None
    source: Literal["catalog", "web"]
    source_domain: str | None
    official_url: str | None
    is_new: bool
    in_review: bool


class ScanOut(BaseModel):
    metrics: dict = Field(default_factory=dict)
    id: str
    region: str
    categories: list[str]
    focus: str
    sites: list[str] = Field(default_factory=list)
    kind: str = "member"
    status: str
    created_at: datetime
    opportunities_found: int = 0
    opportunities_added: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    tasks: list[TaskOut] | None = None
    finds: list[ScanFindOut] | None = None


@router.post(
    "/scans", response_model=ScanOut, dependencies=[Depends(enforce_scan_limit)]
)
async def start_scan(
    req: ScanCreate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Send agents to find new opportunities, one per category."""
    scan = await service.start_scan(
        session,
        current.id,
        categories=[c.value for c in req.categories],
        region=req.region,
        focus=req.focus,
        sites=await service.check_sites(req.sites),
    )
    return await service.scan_detail(session, current.id, scan.id)


class ScanAllowanceOut(BaseModel):
    enabled: bool
    per_hour: int
    left_this_hour: int
    per_day: int
    left_today: int


@router.get("/scans/allowance", response_model=ScanAllowanceOut)
async def scan_allowance(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """How many more scans the member can start, by the same windows the limit enforces."""
    return await service.scan_allowance(session, current.id)


@router.get("/scans", response_model=list[ScanOut])
async def list_scans(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await service.list_scans(session, current.id)


@router.get("/scans/{scan_id}", response_model=ScanOut)
async def get_scan(
    scan_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """The scan with every task's live trace."""
    return await service.scan_detail(session, current.id, scan_id)


@router.post("/scans/{scan_id}/cancel", response_model=ScanOut)
async def cancel_scan(
    scan_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await service.cancel_scan(session, current.id, scan_id)


@router.delete("/scans/{scan_id}")
async def delete_scan(
    scan_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await service.delete_scan(session, current.id, scan_id)


# --- My sources -----------------------------------------------------------------


class MemberSourceIn(BaseModel):
    url: str = Field(min_length=3, max_length=2000)
    category: OpportunityCategory
    note: str = Field(default="", max_length=500)


class MemberSourcePatch(BaseModel):
    category: OpportunityCategory | None = None
    note: str | None = Field(default=None, max_length=500)
    paused: bool | None = None


class MemberSourceOut(BaseModel):
    id: str
    url: str
    category: str
    note: str
    paused: bool
    next_check_at: datetime | None
    last_checked_at: datetime | None
    last_scan_id: str | None
    finds: int
    created_at: datetime


class MemberSourcesOut(BaseModel):
    sources: list[MemberSourceOut]
    max_sources: int
    check_days: int


@router.get("/sources", response_model=MemberSourcesOut)
async def list_member_sources(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """The member's saved sources, checked on a schedule."""
    rows = await sources.list_sources(session, current.id)
    return {
        "sources": [sources.source_out(r) for r in rows],
        "max_sources": settings.member_sources_max,
        "check_days": settings.member_source_check_days,
    }


@router.post("/sources", response_model=MemberSourceOut, status_code=201)
async def add_member_source(
    req: MemberSourceIn,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    row = await sources.add_source(
        session, current.id, url=req.url, category=req.category.value, note=req.note
    )
    return sources.source_out(row)


@router.patch("/sources/{source_id}", response_model=MemberSourceOut)
async def edit_member_source(
    source_id: str,
    req: MemberSourcePatch,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    values = req.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    row = await sources.update_source(session, current.id, source_id, values)
    return sources.source_out(row)


@router.delete("/sources/{source_id}", status_code=204)
async def delete_member_source(
    source_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    await sources.delete_source(session, current.id, source_id)


@router.post("/sources/check", response_model=list[ScanOut], status_code=202)
async def check_member_sources(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Check every active source now; at most once an hour."""
    started = await sources.check_now(session, current.id)
    return [await service.scan_detail(session, current.id, s.id) for s in started]
