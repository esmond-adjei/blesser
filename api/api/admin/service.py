import json
from datetime import UTC, datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from api.admin.audit import audited
from api.applications.models import Application
from api.auth.models import User
from api.core.exceptions import BadRequestError, ConflictError, NotFoundError
from api.core.time import utcnow_naive
from api.editorial import models as m
from api.editorial import service as editorial
from api.opportunities import dedupe
from api.opportunities import service as opportunities
from api.opportunities.crawl_models import CrawlCandidate
from api.opportunities.models import Opportunity
from api.scans.models import Scan, ScanTask
from api.todos.models import Todo


def snapshot(row):
    # Generated columns (opportunities.search_vector) are derived and never loaded.
    return {col.name: getattr(row, col.name) for col in row.__table__.columns if col.computed is None}


async def commit(session):
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(
            "A unique value or referenced record conflicts with this change."
        ) from exc


async def get_opportunity(session, id):
    row = await session.get(Opportunity, id, with_for_update=True)
    if row is None:
        raise NotFoundError("Opportunity not found")
    return row


async def audit_entries(session, **filters):
    query = select(m.AuditLog)
    for key, value in filters.items():
        if value is not None:
            query = query.where(getattr(m.AuditLog, key) == value)
    return query.order_by(m.AuditLog.at.desc(), m.AuditLog.id.desc())


async def opportunity_detail(session, id):
    row = await get_opportunity(session, id)
    history = (
        (
            await session.execute(
                (
                    await audit_entries(
                        session, entity_type="opportunity", entity_id=id
                    )
                ).limit(20)
            )
        )
        .scalars()
        .all()
    )
    excerpt = None
    scan_ids = [row.scan_id] if row.scan_id else []
    latest_check = (
        await session.execute(
            (
                await audit_entries(
                    session,
                    entity_type="opportunity",
                    entity_id=id,
                    action="opportunity.reverify",
                )
            ).limit(1)
        )
    ).scalar_one_or_none()
    if latest_check and latest_check.after:
        scan_ids.append(latest_check.after["scan_id"])
    if scan_ids:
        tasks = (
            (
                await session.execute(
                    select(ScanTask)
                    .where(ScanTask.scan_id.in_(scan_ids))
                    .order_by(ScanTask.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        from api.opportunities.tools import url_key

        for task in tasks:
            for event in json.loads(task.log or "[]"):
                if event.get("tool") == "fetch_page" and url_key(
                    event.get("input", {}).get("url", "")
                ) == url_key(row.source_url):
                    excerpt = event.get("source_excerpt") or None
                    if excerpt:
                        break
            if excerpt:
                break
    return {
        **opportunities.to_out(row),
        "history": [snapshot(h) for h in history],
        "trace_excerpt": excerpt,
    }


async def edit_opportunity(session, row, values, actor):
    values = dict(values)
    if "slug" in values:
        if not values["slug"]:
            values["slug"] = await editorial.new_slug(
                session, values.get("title", row.title)
            )
        await editorial.slug_available(session, values["slug"], row.id)
        if row.slug and row.slug != values["slug"]:
            prior = await session.get(m.SlugHistory, row.slug)
            if prior is None:
                session.add(m.SlugHistory(slug=row.slug, opportunity_id=row.id))
    for key, value in values.items():
        if isinstance(value, datetime):
            value = (
                value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value
            )
        setattr(row, key, value)
    if "deadline" in values and "deadline_date" not in values:
        from api.applications.dates import parse_deadline

        row.deadline_date = parse_deadline(row.deadline)
    if row.status == "published" and row.published_at is None:
        row.published_at = utcnow_naive()
        row.published_by = actor.id
    if (
        row.status == "published"
        and values.get("status") == "published"
        and "review_reason" not in values
    ):
        row.review_reason = None
    row.dedupe_key = await dedupe.key_for(session, row.organization, row.title)
    row.updated_at = utcnow_naive()
    with session.no_autoflush:
        existing = (
            await session.execute(
                select(Opportunity).where(
                    Opportunity.dedupe_key == row.dedupe_key,
                    Opportunity.id != (row.id or ""),
                )
            )
        ).scalar_one_or_none()
    if existing:
        raise ConflictError("An opportunity with this organization and title exists.")
    await session.flush()


#: Text fields a merge copies from the duplicate when the kept listing has none.
_MERGE_FILL = (
    "organization",
    "summary",
    "eligibility",
    "benefits",
    "location",
    "link",
    "source_url",
)


async def merge(session, source, target):
    """Fold a duplicate into the listing to keep, then hide the duplicate.

    Tracking, to-dos, reports, scan results, collection places and crawl candidates move
    to the kept listing; empty fields are filled from the duplicate; its public link
    redirects to the kept listing.
    """
    if source.id == target.id:
        raise BadRequestError("Choose another opportunity to merge into.")
    if target.status == "hidden":
        raise BadRequestError("Choose a listing that is not hidden to keep.")
    for model in (Application, Todo, m.OpportunityReport, CrawlCandidate):
        await session.execute(
            update(model)
            .where(model.opportunity_id == source.id)
            .values(opportunity_id=target.id)
            .execution_options(synchronize_session=False)
        )
    ids = {"source": source.id, "target": target.id}
    for table, columns in (
        ("scan_finds", "scan_id, found_at, source_url"),
        ("collection_items", "collection_id, position"),
    ):
        await session.execute(
            text(
                f"INSERT INTO {table} (opportunity_id, {columns}) "
                f"SELECT :target, {columns} FROM {table} WHERE opportunity_id = :source "
                "ON CONFLICT DO NOTHING"
            ),
            ids,
        )
        await session.execute(
            text(f"DELETE FROM {table} WHERE opportunity_id = :source"), ids
        )
    for field in _MERGE_FILL:
        if not (getattr(target, field) or "").strip() and getattr(source, field):
            setattr(target, field, getattr(source, field))
    if target.deadline_date is None and source.deadline_date is not None:
        target.deadline, target.deadline_date = source.deadline, source.deadline_date
    for field, limit in (("countries", 20), ("requirements", 30), ("tags", 20)):
        target_values = getattr(target, field) or []
        merged = opportunities._clean_list(
            [*target_values, *(getattr(source, field) or [])], limit
        )
        if merged != target_values:
            setattr(target, field, merged)
    if source.verified_at and (
        target.verified_at is None or source.verified_at > target.verified_at
    ):
        target.verified_at = source.verified_at
    await session.execute(
        update(m.SlugHistory)
        .where(m.SlugHistory.opportunity_id == source.id)
        .values(opportunity_id=target.id)
        .execution_options(synchronize_session=False)
    )
    if source.slug and await session.get(m.SlugHistory, source.slug) is None:
        old_slug = source.slug
        source.slug = f"{old_slug}-merged-{source.id[:8]}"[:200]
        await session.flush()
        session.add(m.SlugHistory(slug=old_slug, opportunity_id=target.id))
    source.status = "hidden"
    source.updated_at = target.updated_at = utcnow_naive()
    await session.flush()


async def queue_reverify(session, row, actor):
    from api.scans.notify import notify_work

    scan = Scan(
        user_id=actor.id,
        region=row.location,
        categories=[row.category],
        focus=f"Re-verify only {row.title}: {row.source_url}",
        status="running",
    )
    session.add(scan)
    await session.flush()
    session.add(
        ScanTask(
            scan_id=scan.id,
            user_id=actor.id,
            task_type="reverify_opportunity",
            target=row.id,
        )
    )
    await notify_work(session, scan.id)
    return scan


async def update_user(session, id, values, actor):
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext("staff-roles")))
    )
    row = await session.get(User, id, with_for_update=True)
    if row is None:
        raise NotFoundError("User not found")
    before = await editorial.staff_out(session, row)
    role = values.get("role") or row.role
    disabling = values.get("disabled") is True
    if row.id == actor.id and role != row.role:
        raise BadRequestError("You cannot change your own role.")
    if row.role == "admin" and (role != "admin" or disabling):
        others = await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == "admin", User.disabled_at.is_(None), User.id != row.id)
        )
        if not others:
            raise BadRequestError(
                "The last active admin must remain enabled and an admin."
            )
    row.role = role
    if values.get("disabled") is not None:
        row.disabled_at = utcnow_naive() if values["disabled"] else None
    await session.flush()
    return row, before


async def write_audit(
    session, actor, action, entity_type, entity_id, before, after, request
):
    await audited(
        session, actor, action, entity_type, entity_id, before, after, request
    )
    await commit(session)
