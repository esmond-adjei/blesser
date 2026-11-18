import re
from datetime import date, timedelta

from sqlalchemy import String, cast, func, or_, select

from api.applications import models as application_models
from api.applications import service as application_service
from api.applications.dates import parse_deadline
from api.core.exceptions import ConflictError, NotFoundError
from api.core.time import utcnow_naive
from api.opportunities import models as m
from api.opportunities import schemas

#: Days ahead that count as "closing soon".
CLOSING_SOON_DAYS = 14
MAX_PAGE = 100


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())).strip()


def dedupe_key(organization: str, title: str) -> str:
    """One row per real opportunity, whoever finds it and however they case it."""
    return f"{normalize(organization)}|{normalize(title)}"


def today() -> date:
    return utcnow_naive().date()


def is_open(opp: m.Opportunity, on: date | None = None) -> bool:
    on = on or today()
    if opp.status == "archived":
        return False
    return bool(opp.rolling) or opp.deadline_date is None or opp.deadline_date >= on


def to_out(opp: m.Opportunity, on: date | None = None) -> dict:
    on = on or today()
    days_left = (opp.deadline_date - on).days if opp.deadline_date else None
    return {
        "id": opp.id,
        "slug": opp.slug,
        "audience": opp.audience,
        "found_by": opp.source,
        "closed": opp.status == "archived",
        "is_new": opp.created_at >= utcnow_naive() - timedelta(days=7),
        "published_at": opp.published_at,
        "published_by": opp.published_by,
        "featured_rank": opp.featured_rank,
        "editor_note": opp.editor_note,
        "review_reason": opp.review_reason,
        "created_by": opp.created_by,
        "scan_id": opp.scan_id,
        "dedupe_key": opp.dedupe_key,
        "title": opp.title,
        "organization": opp.organization,
        "category": opp.category,
        "kind": opp.kind,
        "summary": opp.summary,
        "eligibility": opp.eligibility,
        "benefits": opp.benefits,
        "location": opp.location,
        "countries": opp.countries or [],
        "requirements": opp.requirements or [],
        "tags": opp.tags or [],
        "deadline": opp.deadline,
        "deadline_date": opp.deadline_date,
        "rolling": opp.rolling,
        "link": opp.link,
        "source_url": opp.source_url,
        "status": opp.status,
        "source": opp.source,
        "verified_at": opp.verified_at,
        "created_at": opp.created_at,
        "updated_at": opp.updated_at,
        "is_open": is_open(opp, on),
        "days_left": days_left,
    }


def _open_clause(on: date):
    return or_(
        m.Opportunity.rolling.is_(True),
        m.Opportunity.deadline_date.is_(None),
        m.Opportunity.deadline_date >= on,
    )


def _published():
    return m.Opportunity.status == m.OpportunityStatus.published.value


async def list_public(
    session,
    *,
    q: str = "",
    category: str | None = None,
    kind: str | None = None,
    country: str | None = None,
    open_only: bool = True,
    closing_within: int | None = None,
    sort: str = "deadline",
    limit: int = 30,
    offset: int = 0,
    public_only: bool = False,
    new: bool = False,
    audience: str | None = None,
) -> dict:
    on = today()
    filters = [_published()]
    if public_only:
        filters.append(m.Opportunity.audience == "public")
    elif audience:
        filters.append(m.Opportunity.audience == audience)
    if new:
        filters.append(m.Opportunity.created_at >= utcnow_naive() - timedelta(days=7))
    if open_only:
        filters.append(_open_clause(on))
    if category:
        filters.append(m.Opportunity.category == category)
    if kind:
        filters.append(m.Opportunity.kind == kind)
    if country:
        like = f"%{country.strip()}%"
        filters.append(
            or_(
                m.Opportunity.location.ilike(like),
                cast(m.Opportunity.countries, String).ilike(like),
            )
        )
    if closing_within is not None:
        filters.append(m.Opportunity.deadline_date.is_not(None))
        filters.append(m.Opportunity.deadline_date >= on)
        filters.append(m.Opportunity.deadline_date <= _plus_days(on, closing_within))
    for word in [w for w in (q or "").split() if w][:8]:
        like = f"%{word}%"
        filters.append(
            or_(
                m.Opportunity.title.ilike(like),
                m.Opportunity.organization.ilike(like),
                m.Opportunity.summary.ilike(like),
                m.Opportunity.eligibility.ilike(like),
                cast(m.Opportunity.tags, String).ilike(like),
            )
        )
    total = (
        await session.execute(
            select(func.count()).select_from(m.Opportunity).where(*filters)
        )
    ).scalar_one()
    stmt = select(m.Opportunity).where(*filters)
    if sort == "new":
        stmt = stmt.order_by(m.Opportunity.created_at.desc(), m.Opportunity.id)
    else:
        # Soonest real deadline first; rolling and undated after them.
        stmt = stmt.order_by(
            m.Opportunity.deadline_date.asc().nulls_last(),
            m.Opportunity.created_at.desc(),
            m.Opportunity.id,
        )
    limit = max(1, min(limit, MAX_PAGE))
    rows = (
        (await session.execute(stmt.offset(max(offset, 0)).limit(limit)))
        .scalars()
        .all()
    )
    return {"items": [to_out(r, on) for r in rows], "total": total}


def _plus_days(on: date, days: int) -> date:
    return on + timedelta(days=max(days, 0))


async def facets(session, *, public_only=False) -> dict:
    on = today()
    base = [_published(), _open_clause(on)]
    if public_only:
        base.append(m.Opportunity.audience == "public")
    cats = (
        await session.execute(
            select(m.Opportunity.category, func.count())
            .where(*base)
            .group_by(m.Opportunity.category)
        )
    ).all()
    kinds = (
        await session.execute(
            select(m.Opportunity.kind, func.count())
            .where(*base)
            .group_by(m.Opportunity.kind)
        )
    ).all()
    soon = (
        await session.execute(
            select(func.count())
            .select_from(m.Opportunity)
            .where(
                *base,
                m.Opportunity.deadline_date.is_not(None),
                m.Opportunity.deadline_date >= on,
                m.Opportunity.deadline_date <= _plus_days(on, CLOSING_SOON_DAYS),
            )
        )
    ).scalar_one()
    return {
        "categories": [
            {"key": k, "count": c} for k, c in sorted(cats, key=lambda r: -r[1])
        ],
        "kinds": [
            {"key": k, "count": c} for k, c in sorted(kinds, key=lambda r: -r[1])
        ],
        "total": sum(c for _, c in cats),
        "closing_soon": soon,
    }


async def get_or_404(
    session, opportunity_id: str, *, public: bool = True
) -> m.Opportunity:
    opp = (
        await session.execute(
            select(m.Opportunity).where(
                or_(
                    m.Opportunity.id == opportunity_id,
                    m.Opportunity.slug == opportunity_id,
                )
            )
        )
    ).scalar_one_or_none()
    if opp is None or (public and opp.status != "published"):
        raise NotFoundError("Opportunity not found")
    return opp


def _clean_list(values: list[str], limit: int = 20) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        value = re.sub(r"\s+", " ", str(raw or "")).strip()
        if value and normalize(value) not in seen:
            seen.add(normalize(value))
            out.append(value[:200])
        if len(out) >= limit:
            break
    return out


async def find_by_key(session, key: str) -> m.Opportunity | None:
    return (
        await session.execute(
            select(m.Opportunity).where(m.Opportunity.dedupe_key == key)
        )
    ).scalar_one_or_none()


async def submit(session, user_id: str | None, data: schemas.OpportunitySubmit) -> dict:
    """Share an opportunity using the editorial publishing default."""
    key = dedupe_key(data.organization, data.title)
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(key))))
    existing = await find_by_key(session, key)
    if existing is not None:
        if existing.status != "published" and user_id is not None:
            raise ConflictError("This opportunity has already been submitted.")
        return to_out(existing)
    from api.editorial.service import get_settings, new_slug

    default = (await get_settings(session))["community_default"]
    opp = m.Opportunity(
        title=data.title.strip(),
        organization=data.organization.strip(),
        category=data.category.value,
        kind=data.kind.value,
        summary=data.summary.strip(),
        eligibility=data.eligibility.strip(),
        benefits=data.benefits.strip(),
        location=data.location.strip(),
        countries=_clean_list(data.countries),
        requirements=_clean_list(data.requirements, 30),
        tags=_clean_list(data.tags),
        deadline=data.deadline.strip(),
        deadline_date=data.deadline_date or parse_deadline(data.deadline),
        rolling=data.rolling,
        link=data.link.strip(),
        source_url=data.link.strip(),
        status=default["status"],
        audience="members",
        slug=await new_slug(session, data.title),
        review_reason="new_submission" if default["status"] == "in_review" else None,
        published_at=utcnow_naive() if default["status"] == "published" else None,
        source=m.OpportunitySource.community.value,
        dedupe_key=key,
        created_by=user_id,
    )
    session.add(opp)
    await session.commit()
    await session.refresh(opp)
    return to_out(opp)


#: Fields an agent re-read may fill when they are still empty.
_FILLABLE = (
    "organization",
    "summary",
    "eligibility",
    "benefits",
    "location",
    "deadline",
    "link",
)


async def upsert_from_agent(
    session,
    *,
    user_id: str | None,
    scan_id: str | None,
    data: schemas.AgentOpportunityIn,
    low_confidence: bool = False,
) -> tuple[m.Opportunity, bool, list[str]]:
    """Return the grounded row, whether created, and the fields refreshed."""
    key = dedupe_key(data.organization, data.title)
    now = utcnow_naive()
    deadline_date = parse_deadline(data.deadline)
    # Parallel scan tasks can find the same opportunity: serialize on its key until commit.
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(key))))
    from api.opportunities.page_content import normalized_url

    source_key = normalized_url(data.source_url)
    urls = {source_key, normalized_url(data.link)} if data.link else {source_key}
    for url in sorted(urls):
        await session.execute(
            select(func.pg_advisory_xact_lock(func.hashtext("source-save:" + url)))
        )
    opp = await find_by_key(session, key)
    if opp is None:
        rows = (await session.execute(select(m.Opportunity))).scalars().all()
        for row in rows:
            if any(
                value and normalized_url(value) in urls
                for value in (row.source_url, row.link)
            ):
                return row, False, []
    if opp is None:
        from api.editorial.service import get_settings, new_slug

        default = (await get_settings(session))["agent_default"]
        if low_confidence:
            default = {**default, "status": "in_review"}
        opp = m.Opportunity(
            title=data.title.strip(),
            organization=data.organization.strip(),
            category=data.category.value,
            kind=data.kind.value,
            summary=data.summary.strip(),
            eligibility=data.eligibility.strip(),
            benefits=data.benefits.strip(),
            location=data.location.strip(),
            countries=_clean_list(data.countries),
            requirements=_clean_list(data.requirements, 30),
            tags=_clean_list(data.tags),
            deadline=data.deadline.strip(),
            deadline_date=deadline_date,
            rolling=data.rolling,
            link=(data.link or data.source_url).strip(),
            source_url=data.source_url.strip(),
            status=default["status"],
            audience=default["audience"],
            slug=await new_slug(session, data.title),
            review_reason="agent_find" if default["status"] == "in_review" else None,
            published_at=now if default["status"] == "published" else None,
            source=m.OpportunitySource.agent.value,
            dedupe_key=key,
            created_by=user_id,
            scan_id=scan_id,
            verified_at=now,
        )
        session.add(opp)
        await session.flush()
        return opp, True, []
    updated: list[str] = []
    for field in _FILLABLE:
        incoming = (getattr(data, field, "") or "").strip()
        if incoming and not (getattr(opp, field) or "").strip():
            setattr(opp, field, incoming)
            updated.append(field)
    if "deadline" in updated or (
        opp.deadline_date is None and deadline_date is not None
    ):
        opp.deadline_date = deadline_date
        if "deadline" not in updated:
            updated.append("deadline_date")
    # A newer cycle's deadline replaces a passed one: the source page was just read.
    if (
        deadline_date is not None
        and opp.deadline_date is not None
        and opp.deadline_date < today() <= deadline_date
    ):
        opp.deadline = data.deadline.strip()
        opp.deadline_date = deadline_date
        updated.append("deadline")
    for field, limit in (("countries", 20), ("requirements", 30), ("tags", 20)):
        merged = _clean_list(
            [*(getattr(opp, field) or []), *getattr(data, field)], limit
        )
        if merged != (getattr(opp, field) or []):
            setattr(opp, field, merged)
            updated.append(field)
    if data.rolling and not opp.rolling:
        opp.rolling = True
        updated.append("rolling")
    opp.verified_at = now
    await session.flush()
    return opp, False, updated


async def tracked_map(session, user_id: str) -> dict[str, str]:
    """{opportunity_id: application_id} for the person's tracked opportunities."""
    rows = await session.execute(
        select(
            application_models.Application.opportunity_id,
            application_models.Application.id,
        ).where(
            application_models.Application.user_id == user_id,
            application_models.Application.opportunity_id.is_not(None),
        )
    )
    return {opp_id: app_id for opp_id, app_id in rows.all()}


_KIND_LABELS = {
    "call_for_proposals": "Call for proposals",
}


def kind_label(kind: str) -> str:
    return _KIND_LABELS.get(kind, kind.replace("_", " ").capitalize())


async def track(session, user_id: str, opportunity_id: str, *, commit: bool = True) -> tuple[dict, bool]:
    """Copy an opportunity into the person's application tracker; idempotent."""
    opp = await get_or_404(session, opportunity_id, public=False)
    if opp.status != "published":
        from api.scans.models import Scan

        owner = (
            await session.scalar(select(Scan.user_id).where(Scan.id == opp.scan_id))
            if opp.status == "in_review" and opp.scan_id
            else None
        )
        if owner != user_id:
            raise NotFoundError("Opportunity not found")
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(f"track:{user_id}:{opp.id}")))
    )
    existing = (
        await session.execute(
            select(application_models.Application).where(
                application_models.Application.user_id == user_id,
                application_models.Application.opportunity_id == opp.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return application_service.to_out(existing), False
    app = application_models.Application(
        user_id=user_id,
        title=opp.title,
        organization=opp.organization,
        kind=kind_label(opp.kind),
        location=opp.location,
        link=opp.link or opp.source_url,
        benefits=opp.benefits,
        requirements=[{"label": r, "done": False} for r in opp.requirements or []],
        deadline=opp.deadline,
        deadline_date=opp.deadline_date,
        status=application_models.ApplicationStatus.saved.value,
        notes=f"Eligibility: {opp.eligibility}" if opp.eligibility else "",
        opportunity_id=opp.id,
    )
    session.add(app)
    if commit:
        await session.commit()
    else:
        await session.flush()
    await session.refresh(app)
    return application_service.to_out(app), True
