from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin import schemas as s
from api.admin import service
from api.admin.auth import get_admin, get_staff
from api.auth import schemas as auth_schemas
from api.auth import service as auth_service
from api.auth.models import RefreshToken, User
from api.auth.security import hash_token
from api.core.db import get_session, like_pattern
from api.core.exceptions import NotFoundError
from api.editorial import models as m
from api.editorial import service as editorial
from api.opportunities import service as opportunities
from api.opportunities.models import Opportunity
from api.public.schemas import CollectionOut, SiteContent
from api.scans import service as scans
from api.scans.models import Scan
from api.scans.routes import ScanCreate, ScanOut

router = APIRouter(tags=["admin"])


async def staff_session(session, result):
    user = await session.get(User, result["user"]["id"])
    return {**result["tokens"], "user": await editorial.staff_out(session, user)}


@router.post("/auth/login", response_model=s.StaffSession)
async def login(
    req: auth_schemas.LoginIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    result = await auth_service.login(
        session, req.email, req.password, "admin", commit=False
    )
    user = await session.get(User, result["user"]["id"])
    await service.write_audit(
        session,
        user,
        "auth.login",
        "user",
        user.id,
        None,
        {"audience": "admin"},
        request,
    )
    return await staff_session(session, result)


@router.post("/auth/refresh")
async def refresh(
    req: auth_schemas.RefreshIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    result = await auth_service.refresh(
        session, req.refresh_token, "admin", commit=False
    )
    user = await session.get(User, result["user"]["id"])
    await service.write_audit(
        session,
        user,
        "auth.refresh",
        "user",
        user.id,
        None,
        {"audience": "admin"},
        request,
    )
    return {
        "tokens": result["tokens"],
        "user": await editorial.staff_out(session, user),
    }


@router.post("/auth/logout")
async def logout(
    req: auth_schemas.RefreshIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    grant = (
        await session.execute(
            select(RefreshToken)
            .where(
                RefreshToken.token_hash == hash_token(req.refresh_token),
                RefreshToken.audience == "admin",
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    user = await session.get(User, grant.user_id) if grant else None
    result = await auth_service.logout(
        session, req.refresh_token, audience="admin", commit=False
    )
    if user:
        await service.write_audit(
            session,
            user,
            "auth.logout",
            "user",
            user.id,
            {"audience": "admin"},
            None,
            request,
        )
    return result


@router.get("/auth/me", response_model=s.StaffUser)
async def me(
    session: AsyncSession = Depends(get_session), staff: User = Depends(get_staff)
):
    return await editorial.staff_out(session, staff)


@router.get("/opportunities", response_model=s.AdminPage)
async def list_opportunities(
    q: str = Query("", max_length=200),
    status: s.OpportunityStatus | None = None,
    audience: s.Audience | None = None,
    review_reason: s.ReviewReason | None = None,
    category: s.OpportunityCategory | None = None,
    kind: s.OpportunityKind | None = None,
    source: Literal["agent", "community", "staff"] | None = None,
    sort: Literal["updated", "deadline", "created"] = "updated",
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_staff),
):
    filters = []
    for field, value in {
        "status": status,
        "audience": audience,
        "review_reason": review_reason,
        "category": category,
        "kind": kind,
        "source": source,
    }.items():
        if value is not None:
            filters.append(getattr(Opportunity, field) == value)
    if q:
        filters.append(
            or_(
                Opportunity.title.ilike(like_pattern(q)),
                Opportunity.organization.ilike(like_pattern(q)),
            )
        )
    total = await session.scalar(
        select(func.count()).select_from(Opportunity).where(*filters)
    )
    order = {
        "updated": Opportunity.updated_at.desc(),
        "created": Opportunity.created_at.desc(),
        "deadline": Opportunity.deadline_date.asc().nulls_last(),
    }[sort]
    rows = (
        (
            await session.execute(
                select(Opportunity)
                .where(*filters)
                .order_by(order, Opportunity.id)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return {"items": [opportunities.to_out(r) for r in rows], "total": total}


@router.get("/opportunities/counts")
async def counts(
    session: AsyncSession = Depends(get_session), staff: User = Depends(get_staff)
):
    rows = (
        await session.execute(
            select(Opportunity.status, Opportunity.audience, func.count()).group_by(
                Opportunity.status, Opportunity.audience
            )
        )
    ).all()
    out = {
        "in_review": 0,
        "members_only": 0,
        "published_public": 0,
        "archived": 0,
        "hidden": 0,
        "draft": 0,
    }
    for status, audience, count in rows:
        key = (
            ("published_public" if audience == "public" else "members_only")
            if status == "published"
            else status
        )
        out[key] += count
    return out


@router.post("/opportunities", response_model=s.AdminOpportunity)
async def create_opportunity(
    req: s.OpportunityEdit,
    request: Request,
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_staff),
):
    values = req.model_dump(mode="python")
    values["slug"] = values["slug"] or await editorial.new_slug(session, req.title)
    row = Opportunity(
        source="staff",
        created_by=staff.id,
        **values,
        dedupe_key=opportunities.dedupe_key(req.organization, req.title),
    )
    await editorial.slug_available(session, row.slug)
    if await opportunities.find_by_key(session, row.dedupe_key):
        from api.core.exceptions import ConflictError

        raise ConflictError("Opportunity already exists.")
    session.add(row)
    await service.edit_opportunity(session, row, {}, staff)
    await service.write_audit(
        session,
        staff,
        "opportunity.create",
        "opportunity",
        row.id,
        None,
        service.snapshot(row),
        request,
    )
    return opportunities.to_out(row)


@router.post("/opportunities/bulk")
async def bulk(
    req: s.BulkIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_staff),
):
    actions = {
        "publish_public": {"status": "published", "audience": "public"},
        "publish_members": {"status": "published", "audience": "members"},
        "archive": {"status": "archived"},
        "hide": {"status": "hidden"},
        "to_review": {"status": "in_review"},
    }
    rows = [await service.get_opportunity(session, id) for id in sorted(set(req.ids))]
    from api.admin.audit import audited

    for row in rows:
        before = service.snapshot(row)
        await service.edit_opportunity(session, row, actions[req.action], staff)
        await audited(
            session,
            staff,
            f"opportunity.bulk.{req.action}",
            "opportunity",
            row.id,
            before,
            service.snapshot(row),
            request,
        )
    await service.commit(session)
    return {"updated": len(rows)}


@router.get("/opportunities/{id}", response_model=s.AdminDetail)
async def opportunity(
    id: str,
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_staff),
):
    return await service.opportunity_detail(session, id)


@router.patch("/opportunities/{id}", response_model=s.AdminOpportunity)
async def patch_opportunity(
    id: str,
    req: s.OpportunityPatch,
    request: Request,
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_staff),
):
    row = await service.get_opportunity(session, id)
    before = service.snapshot(row)
    await service.edit_opportunity(
        session, row, req.model_dump(exclude_unset=True), staff
    )
    await service.write_audit(
        session,
        staff,
        "opportunity.update",
        "opportunity",
        id,
        before,
        service.snapshot(row),
        request,
    )
    return opportunities.to_out(row)


@router.delete("/opportunities/{id}")
async def delete_opportunity(
    id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_staff),
):
    row = await service.get_opportunity(session, id)
    before = service.snapshot(row)
    await session.delete(row)
    await service.write_audit(
        session, staff, "opportunity.delete", "opportunity", id, before, None, request
    )
    return {"status": "deleted"}


@router.post("/opportunities/{id}/merge", response_model=s.AdminOpportunity)
async def merge(
    id: str,
    req: s.MergeIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_staff),
):
    rows = {
        i: await service.get_opportunity(session, i) for i in sorted({id, req.into_id})
    }
    row, target = rows[id], rows[req.into_id]
    before = service.snapshot(row)
    await service.merge(session, row, target)
    await service.write_audit(
        session,
        staff,
        "opportunity.merge",
        "opportunity",
        id,
        before,
        {**service.snapshot(row), "into_id": target.id},
        request,
    )
    return opportunities.to_out(target)


@router.post("/opportunities/{id}/reverify", status_code=202)
async def reverify(
    id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_staff),
):
    row = await service.get_opportunity(session, id)
    scan = await service.queue_reverify(session, row, staff)
    await service.write_audit(
        session,
        staff,
        "opportunity.reverify",
        "opportunity",
        id,
        None,
        {"scan_id": scan.id},
        request,
    )
    return {"scan_id": scan.id}


@router.get("/reports", response_model=list[s.ReportOut])
async def reports(
    session: AsyncSession = Depends(get_session), staff: User = Depends(get_staff)
):
    return [
        service.snapshot(r)
        for r in (
            await session.execute(
                select(m.OpportunityReport).order_by(
                    m.OpportunityReport.created_at.desc()
                )
            )
        ).scalars()
    ]


@router.patch("/reports/{id}", response_model=s.ReportOut)
async def resolve_report(
    id: str,
    req: s.ReportPatch,
    request: Request,
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_staff),
):
    row = await session.get(m.OpportunityReport, id, with_for_update=True)
    if row is None:
        raise NotFoundError("Report not found")
    before = service.snapshot(row)
    row.resolved = req.resolved
    await service.write_audit(
        session,
        staff,
        "report.resolve",
        "report",
        id,
        before,
        service.snapshot(row),
        request,
    )
    return service.snapshot(row)


@router.get("/collections", response_model=list[CollectionOut])
async def collections(
    session: AsyncSession = Depends(get_session), staff: User = Depends(get_staff)
):
    rows = (
        (
            await session.execute(
                select(m.Collection).order_by(m.Collection.position, m.Collection.id)
            )
        )
        .scalars()
        .all()
    )
    return [await editorial.collection_out(session, r) for r in rows]


@router.post("/collections", response_model=CollectionOut)
async def create_collection(
    req: s.CollectionCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_staff),
):
    values = req.model_dump()
    ids = values.pop("item_ids")
    if values["filter"] is not None:
        editorial.validate_filter(values["filter"])
    row = m.Collection(**values)
    session.add(row)
    await session.flush()
    await editorial.set_items(session, row, ids)
    out = await editorial.collection_out(session, row)
    await service.write_audit(
        session, staff, "collection.create", "collection", row.id, None, out, request
    )
    return out


@router.patch("/collections/{id}", response_model=CollectionOut)
async def patch_collection(
    id: str,
    req: s.CollectionPatch,
    request: Request,
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_staff),
):
    row = await session.get(m.Collection, id, with_for_update=True)
    if row is None:
        raise NotFoundError("Collection not found")
    before = await editorial.collection_out(session, row)
    values = req.model_dump(exclude_unset=True)
    if values.get("filter") is not None:
        editorial.validate_filter(values["filter"])
    ids = values.pop("item_ids", None)
    for key, value in values.items():
        setattr(row, key, value)
    if ids is not None:
        await editorial.set_items(session, row, ids)
    out = await editorial.collection_out(session, row)
    await service.write_audit(
        session, staff, "collection.update", "collection", id, before, out, request
    )
    return out


@router.delete("/collections/{id}")
async def delete_collection(
    id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_staff),
):
    row = await session.get(m.Collection, id, with_for_update=True)
    if row is None:
        raise NotFoundError("Collection not found")
    before = await editorial.collection_out(session, row)
    await session.delete(row)
    await service.write_audit(
        session, staff, "collection.delete", "collection", id, before, None, request
    )
    return {"status": "deleted"}


@router.get("/site", response_model=SiteContent)
async def site(
    session: AsyncSession = Depends(get_session), staff: User = Depends(get_staff)
):
    return await editorial.content(session)


@router.put("/site", response_model=SiteContent)
async def update_site(
    req: SiteContent,
    request: Request,
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_staff),
):
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext("site-content")))
    )
    before = await editorial.content(session)
    version = (
        await session.scalar(
            select(func.max(m.SiteContent.version)).where(m.SiteContent.key == "site")
        )
        or 0
    ) + 1
    row = m.SiteContent(
        key="site", version=version, value=req.model_dump(mode="json"), published=True
    )
    session.add(row)
    await session.flush()
    await service.write_audit(
        session,
        staff,
        "site.update",
        "site_content",
        row.id,
        before,
        row.value,
        request,
    )
    return row.value


@router.get("/settings", response_model=s.SettingsIn)
async def settings(
    session: AsyncSession = Depends(get_session), staff: User = Depends(get_admin)
):
    return await editorial.get_settings(session)


@router.put("/settings", response_model=s.SettingsIn)
async def update_settings(
    req: s.SettingsIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_admin),
):
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext("site-settings")))
    )
    before = await editorial.get_settings(session)
    values = req.model_dump(mode="json")
    for key, value in values.items():
        row = await session.get(m.SiteSetting, key)
        if row:
            row.value = value
        else:
            session.add(m.SiteSetting(key=key, value=value))
    await service.write_audit(
        session,
        staff,
        "settings.update",
        "site_settings",
        "settings",
        before,
        values,
        request,
    )
    return values


@router.get("/scans")
async def list_scans(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_staff),
):
    rows = (
        await session.execute(
            select(Scan, User.email)
            .join(User, User.id == Scan.user_id)
            .order_by(Scan.created_at.desc(), Scan.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [
        {**await scans.scan_detail(session, row.user_id, row.id), "owner_email": email}
        for row, email in rows
    ]


@router.post("/scans", response_model=ScanOut)
async def start_scan(
    req: ScanCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_staff),
):
    scan = await scans.start_scan(
        session,
        staff.id,
        categories=[c.value for c in req.categories],
        region=req.region,
        focus=req.focus,
        commit=False,
    )
    await service.write_audit(
        session,
        staff,
        "scan.create",
        "scan",
        scan.id,
        None,
        service.snapshot(scan),
        request,
    )
    return await scans.scan_detail(session, staff.id, scan.id)


@router.get("/users", response_model=s.UserPage)
async def users(
    q: str = Query("", max_length=200),
    role: Literal["member", "editor", "admin"] | None = None,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_admin),
):
    filters = []
    if q:
        filters.append(
            or_(
                User.email.ilike(like_pattern(q)),
                User.display_name.ilike(like_pattern(q)),
            )
        )
    if role:
        filters.append(User.role == role)
    total = await session.scalar(select(func.count()).select_from(User).where(*filters))
    rows = (
        (
            await session.execute(
                select(User)
                .where(*filters)
                .order_by(User.created_at.desc(), User.id)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [await editorial.staff_out(session, r) for r in rows],
        "total": total,
    }


@router.patch("/users/{id}", response_model=s.StaffUser)
async def patch_user(
    id: str,
    req: s.UserPatch,
    request: Request,
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_admin),
):
    row, before = await service.update_user(
        session, id, req.model_dump(exclude_unset=True), staff
    )
    after = await editorial.staff_out(session, row)
    await service.write_audit(
        session,
        staff,
        "user.role" if req.role else "user.disable",
        "user",
        id,
        before,
        after,
        request,
    )
    return after


@router.get("/audit", response_model=s.AuditPage)
async def audit(
    actor_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    staff: User = Depends(get_admin),
):
    query = await service.audit_entries(
        session,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
    )
    total = await session.scalar(
        select(func.count()).select_from(query.order_by(None).subquery())
    )
    rows = (await session.execute(query.limit(limit).offset(offset))).scalars().all()
    return {"items": [service.snapshot(r) for r in rows], "total": total}
