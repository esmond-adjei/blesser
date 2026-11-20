"""My sources: sites a member saves so Blesser checks them on a schedule.

A check is an ordinary scan of kind `sources`: the agent reads the member's sites
(no web search), matches the catalogue and saves new finds, which wait for staff
review unless the site is already an enabled staff source. Checks never use the
member's scan quota; "check now" is limited to once an hour.
"""

from datetime import timedelta
from urllib.parse import urlsplit

from sqlalchemy import distinct, func, select

from api.auth.models import User
from api.core.config import settings
from api.core.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    RateLimitError,
)
from api.core.time import utcnow_naive
from api.opportunities.models import OpportunityCategory
from api.opportunities.page_content import normalized_url
from api.scans import models as m
from api.scans.service import check_sites, start_scan

SOURCES_KIND = "sources"
CHECK_NOW_COOLDOWN = timedelta(hours=1)


def source_out(row: m.MemberSource) -> dict:
    return {
        "id": row.id,
        "url": row.url,
        "category": row.category,
        "note": row.note,
        "paused": row.paused,
        "next_check_at": None if row.paused else row.next_check_at,
        "last_checked_at": row.last_checked_at,
        "last_scan_id": row.last_scan_id,
        "finds": row.finds,
        "created_at": row.created_at,
    }


async def list_sources(session, user_id: str) -> list[m.MemberSource]:
    return list(
        (
            await session.execute(
                select(m.MemberSource)
                .where(m.MemberSource.user_id == user_id)
                .order_by(m.MemberSource.created_at, m.MemberSource.id)
            )
        )
        .scalars()
        .all()
    )


async def _get(session, user_id: str, source_id: str) -> m.MemberSource:
    row = await session.get(m.MemberSource, source_id)
    if row is None or row.user_id != user_id:
        raise NotFoundError("Source not found")
    return row


def _category(value: str) -> str:
    try:
        return OpportunityCategory(value).value
    except ValueError as exc:
        raise BadRequestError("Choose startups, research or students.") from exc


async def add_source(
    session, user_id: str, *, url: str, category: str, note: str = ""
) -> m.MemberSource:
    sites = await check_sites([url])
    if not sites:
        raise BadRequestError("Enter a site address.", field="url")
    site = sites[0]
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext("member-sources:" + user_id)))
    )
    count = await session.scalar(
        select(func.count())
        .select_from(m.MemberSource)
        .where(m.MemberSource.user_id == user_id)
    )
    if (count or 0) >= settings.member_sources_max:
        raise BadRequestError(
            f"You can save up to {settings.member_sources_max} sources. "
            "Remove one to add another.",
            field="url",
        )
    key = normalized_url(site)
    exists = await session.scalar(
        select(m.MemberSource.id).where(
            m.MemberSource.user_id == user_id, m.MemberSource.url_key == key
        )
    )
    if exists:
        raise ConflictError("This site is already in your sources.")
    row = m.MemberSource(
        user_id=user_id,
        url=site,
        url_key=key,
        category=_category(category),
        note=note.strip(),
        paused=False,
        finds=0,
        # The first check runs on the next hourly pass.
        next_check_at=utcnow_naive(),
    )
    session.add(row)
    await session.commit()
    return row


async def update_source(
    session, user_id: str, source_id: str, values: dict
) -> m.MemberSource:
    row = await _get(session, user_id, source_id)
    if "category" in values:
        row.category = _category(values["category"])
    if "note" in values:
        row.note = (values["note"] or "").strip()
    if "paused" in values:
        resumed = row.paused and not values["paused"]
        row.paused = bool(values["paused"])
        if resumed and row.next_check_at < utcnow_naive():
            row.next_check_at = utcnow_naive()
    await session.commit()
    return row


async def delete_source(session, user_id: str, source_id: str) -> None:
    row = await _get(session, user_id, source_id)
    await session.delete(row)
    await session.commit()


def _focus(rows: list[m.MemberSource]) -> str:
    notes = [f"{row.url}: {row.note}" for row in rows if row.note]
    text = "Scheduled check of the member's saved sources."
    if notes:
        text += " What they want from each:\n" + "\n".join(notes)
    return text[:2000]


async def start_checks(
    session, user_id: str, *, due_only: bool, now=None
) -> list[m.Scan]:
    """Start one sources scan per category with active sources. Commits."""
    now = now or utcnow_naive()
    query = select(m.MemberSource).where(
        m.MemberSource.user_id == user_id, m.MemberSource.paused.is_(False)
    )
    if due_only:
        query = query.where(m.MemberSource.next_check_at <= now)
    rows = list(
        (await session.execute(query.order_by(m.MemberSource.created_at)))
        .scalars()
        .all()
    )
    by_category: dict[str, list[m.MemberSource]] = {}
    for row in rows:
        by_category.setdefault(row.category, []).append(row)
    started = []
    for category, group in by_category.items():
        scan = await start_scan(
            session,
            user_id,
            categories=[category],
            focus=_focus(group),
            sites=[row.url for row in group],
            kind=SOURCES_KIND,
            commit=False,
        )
        for row in group:
            row.last_checked_at = now
            row.next_check_at = now + timedelta(
                days=max(1, settings.member_source_check_days)
            )
            row.last_scan_id = scan.id
        started.append(scan)
    await session.commit()
    return started


async def check_now(session, user_id: str) -> list[m.Scan]:
    recent = await session.scalar(
        select(func.count())
        .select_from(m.Scan)
        .where(
            m.Scan.user_id == user_id,
            m.Scan.kind == SOURCES_KIND,
            m.Scan.created_at > utcnow_naive() - CHECK_NOW_COOLDOWN,
        )
    )
    if recent:
        raise RateLimitError(
            "Your sources were checked in the last hour. Try again later.",
            retry_after=int(CHECK_NOW_COOLDOWN.total_seconds()),
        )
    scans = await start_checks(session, user_id, due_only=False)
    if not scans:
        raise BadRequestError("Add a source, or resume a paused one, first.")
    return scans


async def check_due_sources(session) -> int:
    """Hourly: start checks for members whose sources are due. Returns scans started."""
    limit = settings.member_source_checks_per_hour
    if limit <= 0:
        return 0
    now = utcnow_naive()
    running = (
        select(m.Scan.id)
        .where(
            m.Scan.user_id == m.MemberSource.user_id,
            m.Scan.kind == SOURCES_KIND,
            m.Scan.status == "running",
        )
        .exists()
    )
    user_ids = (
        (
            await session.execute(
                select(distinct(m.MemberSource.user_id))
                .join(User, User.id == m.MemberSource.user_id)
                .where(
                    m.MemberSource.paused.is_(False),
                    m.MemberSource.next_check_at <= now,
                    User.disabled_at.is_(None),
                    ~running,
                )
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    started = 0
    for user_id in user_ids:
        started += len(await start_checks(session, user_id, due_only=True, now=now))
    return started


def _host(url: str | None) -> str:
    return (urlsplit(url or "").hostname or "").lower().removeprefix("www.")


async def record_finds(session, scan: m.Scan) -> None:
    """After a sources scan: credit each source with the new listings found on it."""
    if scan.kind != SOURCES_KIND:
        return
    urls = (
        (
            await session.execute(
                select(m.ScanFind.source_url).where(
                    m.ScanFind.scan_id == scan.id, m.ScanFind.created.is_(True)
                )
            )
        )
        .scalars()
        .all()
    )
    if not urls:
        return
    rows = (
        (
            await session.execute(
                select(m.MemberSource).where(
                    m.MemberSource.user_id == scan.user_id,
                    m.MemberSource.last_scan_id == scan.id,
                )
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        host = _host(row.url)
        row.finds += sum(
            1 for url in urls if _host(url) == host or _host(url).endswith("." + host)
        )
