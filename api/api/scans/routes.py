"""Scan routes: start agent scans for opportunities and watch them work."""

from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.core.config import settings
from api.core.db import get_session
from api.core.exceptions import ConflictError
from api.core.ratelimit import enforce_scan_limit
from api.opportunities.models import OpportunityCategory, OpportunityKind
from api.scans import schedules, service, sources

router = APIRouter(tags=["scans"])


class ScanCreate(BaseModel):
    # One audience per scan keeps each agent's search precise.
    categories: list[OpportunityCategory] = Field(min_length=1, max_length=1)
    region: str = Field(default="", max_length=120)
    kinds: list[OpportunityKind] = Field(
        default_factory=list,
        max_length=3,
        description="Optional: listing types to look for, such as scholarship or job.",
    )
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
    repeat: bool = Field(
        default=False, description="Repeat this scan every week from now on."
    )


class ScanRerun(BaseModel):
    """What to change when running a scan again; anything left out stays as it was."""

    model_config = ConfigDict(extra="forbid")

    categories: list[OpportunityCategory] | None = Field(
        default=None, min_length=1, max_length=1
    )
    region: str | None = Field(default=None, max_length=120)
    kinds: list[OpportunityKind] | None = Field(default=None, max_length=3)
    focus: str | None = Field(default=None, max_length=2000)
    sites: list[Annotated[str, Field(max_length=2000)]] | None = Field(
        default=None, max_length=service.MAX_SCAN_SITES
    )


class ScanSteer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]


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
    kinds: list[str] = Field(default_factory=list)
    sites: list[str] = Field(default_factory=list)
    kind: str = "member"
    status: str
    created_at: datetime
    opportunities_found: int = 0
    opportunities_added: int
    opportunities_updated: int = 0
    schedule_id: str | None = None
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
    sites = await service.check_sites(req.sites)
    categories = [c.value for c in req.categories]
    if req.repeat:
        # Refuse before the scan starts, so a full or duplicate schedule costs nothing.
        await schedules.ensure_can_repeat(
            session,
            current.id,
            categories=categories,
            region=req.region,
            focus=req.focus,
            sites=sites,
            kinds=[k.value for k in req.kinds],
        )
    scan = await service.start_scan(
        session,
        current.id,
        categories=categories,
        region=req.region,
        focus=req.focus,
        kinds=[k.value for k in req.kinds],
        kind="member",
        sites=sites,
    )
    if req.repeat:
        await schedules.repeat_scan(session, current.id, scan.id)
    return await service.scan_detail(session, current.id, scan.id)


@router.post(
    "/scans/{scan_id}/rerun",
    response_model=ScanOut,
    status_code=201,
    dependencies=[Depends(enforce_scan_limit)],
)
async def rerun_scan(
    scan_id: str,
    req: ScanRerun,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Start a new scan from this one, optionally with a changed brief."""
    original = await service.get_or_404(session, current.id, scan_id)
    if original.kind not in ("member", "scheduled"):
        raise ConflictError("This scan can't be run again.")
    fields = req.model_dump(exclude_unset=True)
    categories = (
        [c.value for c in req.categories] if req.categories else original.categories
    )
    sites = (
        await service.check_sites(req.sites)
        if req.sites is not None
        else list(original.sites or [])
    )
    scan = await service.start_scan(
        session,
        current.id,
        categories=categories,
        region=fields.get("region") if "region" in fields else original.region,
        focus=fields.get("focus") if "focus" in fields else original.focus,
        kinds=[k.value for k in req.kinds]
        if req.kinds is not None
        else list(original.kinds or []),
        sites=sites,
        kind="member",
    )
    return await service.scan_detail(session, current.id, scan.id)


@router.post(
    "/scans/{scan_id}/steer",
    response_model=ScanOut,
    dependencies=[Depends(enforce_scan_limit)],
)
async def steer_scan(
    scan_id: str,
    req: ScanSteer,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Run the scan again with a note on what to look for or avoid."""
    await service.steer_scan(session, current.id, scan_id, req.prompt)
    return await service.scan_detail(session, current.id, scan_id)


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


# --- Repeating scans -----------------------------------------------------------------


class ScheduleRunOut(BaseModel):
    scan_id: str
    status: str
    created_at: datetime
    new: int
    updated: int


class ScheduleOut(BaseModel):
    id: str
    audience: Literal["member", "staff"]
    name: str
    categories: list[str]
    region: str
    focus: str
    kinds: list[str] = Field(default_factory=list)
    sites: list[str]
    interval_hours: int
    paused: bool
    pause_reason: Literal["empty", "inactive"] | None
    next_run_at: datetime | None
    last_run_at: datetime | None
    runs: int
    last_run: ScheduleRunOut | None
    created_at: datetime


class SchedulesOut(BaseModel):
    schedules: list[ScheduleOut]
    max_schedules: int
    interval_hours: int


class SchedulePatch(BaseModel):
    paused: bool | None = None
    focus: str | None = Field(default=None, max_length=2000)
    sites: list[Annotated[str, Field(max_length=2000)]] | None = Field(
        default=None, max_length=service.MAX_SCAN_SITES
    )


@router.get("/scans/schedules", response_model=SchedulesOut)
async def list_schedules(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """The member's repeating scans."""
    rows = await schedules.list_member(session, current.id)
    return {
        "schedules": [await schedules.schedule_out(session, r) for r in rows],
        "max_schedules": await schedules.member_limit(session),
        "interval_hours": schedules.MEMBER_INTERVAL_HOURS,
    }


@router.patch("/scans/schedules/{schedule_id}", response_model=ScheduleOut)
async def edit_schedule(
    schedule_id: str,
    req: SchedulePatch,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Pause, resume, or change the focus or sites of a repeating scan."""
    values = req.model_dump(exclude_unset=True, exclude_none=True)
    row = await schedules.update_member(session, current.id, schedule_id, values)
    return await schedules.schedule_out(session, row)


@router.delete("/scans/schedules/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Stop repeating; the scans it ran and what they found stay."""
    await schedules.delete_member(session, current.id, schedule_id)


@router.post("/scans/{scan_id}/repeat", response_model=ScheduleOut, status_code=201)
async def repeat_scan(
    scan_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Repeat one of the member's scans every week, starting a week after it ran."""
    row = await schedules.repeat_scan(session, current.id, scan_id)
    return await schedules.schedule_out(session, row)


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
