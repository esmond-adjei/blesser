from datetime import datetime
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin import service
from api.admin.auth import get_staff
from api.auth.models import User
from api.core import egress
from api.core.db import get_session
from api.core.exceptions import BadRequestError, ConflictError, NotFoundError
from api.core.time import utcnow_naive
from api.opportunities.crawl_models import Source
from api.opportunities.models import OpportunityCategory
from api.opportunities.page_content import normalized_url
from api.public.schemas import APIModel

router = APIRouter(tags=["sources"])


class SourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=8, max_length=2000)
    kind: Literal["rss", "sitemap", "listing"]
    category_hints: list[OpportunityCategory] = Field(
        default_factory=list, max_length=3
    )
    enabled: bool = True

    @field_validator("url")
    @classmethod
    def clean_url(cls, value):
        return value.strip() if value is not None else value


class SourcePatch(SourceIn):
    url: str | None = Field(default=None, min_length=8, max_length=2000)
    kind: Literal["rss", "sitemap", "listing"] | None = None
    category_hints: list[OpportunityCategory] | None = Field(default=None, max_length=3)
    enabled: bool | None = None


class SourceOut(SourceIn, APIModel):
    id: str
    proposed: bool
    last_crawled_at: datetime | None
    next_crawl_at: datetime
    crawl_requested: bool
    etag: str
    last_modified: str
    consecutive_failures: int
    last_error: str
    candidates_found: int
    opportunities_saved: int
    last_candidates: int
    created_at: datetime


async def get_source(session, id):
    row = await session.get(Source, id, with_for_update=True)
    if row is None:
        raise NotFoundError("Source not found")
    return row


async def check_source_url(session, url, id=None):
    try:
        await egress.check_url(url)
    except (egress.EgressBlocked, ValueError, httpx.HTTPError, httpx.InvalidURL) as exc:
        raise BadRequestError("Source must be a public http(s) URL.") from exc
    await session.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtext("source-url:" + normalized_url(url))
            )
        )
    )
    rows = (await session.execute(select(Source.id, Source.url))).all()
    if any(
        row.id != id and normalized_url(row.url) == normalized_url(url) for row in rows
    ):
        raise ConflictError("This source already exists.")


@router.get("/sources", response_model=list[SourceOut])
async def list_sources(
    session: AsyncSession = Depends(get_session), staff: User = Depends(get_staff)
):
    return (
        (
            await session.execute(
                select(Source).order_by(Source.enabled.desc(), Source.created_at)
            )
        )
        .scalars()
        .all()
    )


@router.post("/sources", response_model=SourceOut, status_code=201)
async def create_source(
    req: SourceIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_staff),
):
    await check_source_url(session, req.url)
    row = Source(**req.model_dump(mode="json"))
    session.add(row)
    await session.flush()
    await service.write_audit(
        session,
        staff,
        "source.create",
        "source",
        row.id,
        None,
        service.snapshot(row),
        request,
    )
    return row


@router.patch("/sources/{id}", response_model=SourceOut)
async def edit_source(
    id: str,
    req: SourcePatch,
    request: Request,
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_staff),
):
    row = await get_source(session, id)
    before = service.snapshot(row)
    values = req.model_dump(mode="json", exclude_unset=True)
    if any(value is None for value in values.values()):
        raise BadRequestError("Source fields cannot be null.")
    if "kind" in values:
        row.etag = row.last_modified = ""
    if "url" in values:
        await check_source_url(session, values["url"], id)
        row.etag = row.last_modified = ""
    for key, value in values.items():
        setattr(row, key, value)
    row.next_crawl_at = utcnow_naive()
    await service.write_audit(
        session,
        staff,
        "source.update",
        "source",
        row.id,
        before,
        service.snapshot(row),
        request,
    )
    return row


@router.delete("/sources/{id}", status_code=204)
async def delete_source(
    id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_staff),
):
    row = await get_source(session, id)
    before = service.snapshot(row)
    await session.delete(row)
    await service.write_audit(
        session, staff, "source.delete", "source", id, before, None, request
    )


@router.post("/sources/{id}/crawl", response_model=SourceOut, status_code=202)
async def crawl_source(
    id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_staff),
):
    row = await get_source(session, id)
    if not row.enabled:
        raise BadRequestError("Enable the source before requesting a crawl.")
    before = service.snapshot(row)
    row.crawl_requested = True
    row.next_crawl_at = utcnow_naive()
    await service.write_audit(
        session,
        staff,
        "source.crawl",
        "source",
        id,
        before,
        service.snapshot(row),
        request,
    )
    return row
