from datetime import timedelta

from sqlalchemy import delete, func, select

from api.core.config import settings
from api.core.exceptions import BadRequestError, ConflictError, NotFoundError
from api.core.time import utcnow_naive
from api.editorial import models as m
from api.opportunities import service as opportunities
from api.opportunities.models import Opportunity
from api.public.schemas import SiteContent


def defaults():
    return {
        "agent_default": {"status": "published", "audience": "members"},
        "community_default": {"status": "in_review"},
        "auto_archive": True,
        "member_scan_limits": {"per_hour": 3, "per_day": 10},
        "sweep_hours": settings.opportunity_sweep_hours,
        "crawler": {
            "hours": settings.crawl_hours,
            "max_sources": settings.crawl_max_sources,
            "max_items_per_source": settings.crawl_max_items_per_source,
            "max_candidates_per_task": settings.crawl_max_candidates_per_task,
            "host_interval_seconds": settings.crawl_host_interval_seconds,
            "page_cache_seconds": settings.fetch_cache_seconds,
        },
    }


async def get_settings(session):
    rows = (await session.execute(select(m.SiteSetting))).scalars().all()
    values = defaults()
    return {**values, **{r.key: r.value for r in rows if r.key in values}}


async def slug_available(session, slug, opportunity_id=None):
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext("opportunity-slugs")))
    )
    current = (
        await session.execute(select(Opportunity.id).where(Opportunity.slug == slug))
    ).scalar_one_or_none()
    old = await session.get(m.SlugHistory, slug)
    if (current is not None and current != opportunity_id) or (
        old is not None and old.opportunity_id != opportunity_id
    ):
        raise ConflictError("Slug is already in use.")


async def new_slug(session, title):
    base = (
        opportunities.normalize(title).replace(" ", "-")[:250].rstrip("-")
        or "opportunity"
    )
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext("opportunity-slugs")))
    )
    slug, suffix = base, 1
    while (
        await session.execute(select(Opportunity.id).where(Opportunity.slug == slug))
    ).first() or await session.get(m.SlugHistory, slug):
        suffix += 1
        slug = f"{base}-{suffix}"
    return slug


async def content(session, *, active=False):
    row = (
        await session.execute(
            select(m.SiteContent)
            .where(m.SiteContent.key == "site", m.SiteContent.published.is_(True))
            .order_by(m.SiteContent.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    value = SiteContent.model_validate(row.value if row else {}).model_dump(mode="json")
    banner = value["announcement"]
    today = utcnow_naive().date().isoformat()
    if (
        active
        and banner
        and (
            (banner["starts_on"] and banner["starts_on"] > today)
            or (banner["ends_on"] and banner["ends_on"] < today)
        )
    ):
        value["announcement"] = None
    return value


async def collection_out(session, row, *, public=False, limit=None):
    ids = list(
        (
            await session.execute(
                select(m.CollectionItem.opportunity_id)
                .where(m.CollectionItem.collection_id == row.id)
                .order_by(m.CollectionItem.position, m.CollectionItem.opportunity_id)
            )
        ).scalars()
    )
    out = {
        key: getattr(row, key)
        for key in (
            "id",
            "slug",
            "title",
            "intro",
            "audience",
            "filter",
            "position",
            "published",
        )
    }
    out["item_ids"] = ids
    if public:
        filters = [Opportunity.status == "published", Opportunity.audience == "public"]
        if row.filter is not None:
            params = validate_filter(row.filter)
            results = await opportunities.list_public(
                session, public_only=True, limit=100, **params
            )
            items = results["items"]
            if limit is None and results["total"] > 100:
                for offset in range(100, results["total"], 100):
                    items.extend(
                        (
                            await opportunities.list_public(
                                session,
                                public_only=True,
                                limit=100,
                                offset=offset,
                                **params,
                            )
                        )["items"]
                    )
        else:
            rows = (
                (
                    await session.execute(
                        select(Opportunity).where(*filters, Opportunity.id.in_(ids))
                    )
                )
                .scalars()
                .all()
            )
            by_id = {r.id: opportunities.to_out(r) for r in rows}
            items = [by_id[i] for i in ids if i in by_id]
        out["items"] = items[:limit] if limit else items
        out["item_ids"] = [r["id"] for r in out["items"]]
    return out


def validate_filter(value):
    from typing import Literal

    from pydantic import BaseModel, ConfigDict, Field

    from api.opportunities.models import OpportunityCategory, OpportunityKind

    class Filters(BaseModel):
        model_config = ConfigDict(extra="forbid")
        q: str = Field(default="", max_length=200)
        category: OpportunityCategory | None = None
        kind: OpportunityKind | None = None
        country: str | None = Field(default=None, max_length=80)
        closing_within: int | None = Field(default=None, ge=0, le=365)
        sort: Literal["deadline", "new"] = "deadline"

    try:
        return Filters.model_validate(value).model_dump(mode="json")
    except ValueError as exc:
        raise BadRequestError("Invalid collection filter.") from exc


async def set_items(session, row, ids):
    ids = list(dict.fromkeys(ids))
    existing = set(
        (
            await session.execute(select(Opportunity.id).where(Opportunity.id.in_(ids)))
        ).scalars()
    )
    if existing != set(ids):
        raise NotFoundError("Collection opportunity not found.")
    await session.execute(
        delete(m.CollectionItem).where(m.CollectionItem.collection_id == row.id)
    )
    session.add_all(
        [
            m.CollectionItem(collection_id=row.id, opportunity_id=i, position=p)
            for p, i in enumerate(ids)
        ]
    )
    await session.flush()


async def staff_out(session, user):
    from api.scans.models import Scan

    count = await session.scalar(
        select(func.count())
        .select_from(Scan)
        .where(
            Scan.user_id == user.id,
            Scan.created_at >= utcnow_naive() - timedelta(days=30),
        )
    )
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "email_verified": user.email_verified_at is not None,
        "disabled": user.disabled_at is not None,
        "created_at": user.created_at,
        "scans_last_30_days": count,
    }
