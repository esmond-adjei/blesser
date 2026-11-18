"""Scan routes: start agent scans for opportunities and watch them work."""

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.core.db import get_session
from api.core.ratelimit import enforce_scan_limit
from api.opportunities.models import OpportunityCategory
from api.scans import service

router = APIRouter(tags=["scans"])


class ScanCreate(BaseModel):
    categories: list[OpportunityCategory] = Field(
        default_factory=lambda: list(OpportunityCategory)
    )
    region: str = Field(default="", max_length=120)
    focus: str = Field(
        default="",
        max_length=2000,
        description="Optional: sectors, fields or kinds to look for first.",
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
    status: str
    created_at: datetime
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
