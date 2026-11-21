"""Scan schedules: scans that repeat on their own.

A schedule is a saved scan request plus an interval. The worker's hourly pass starts
the due ones (`run_due`), each as an ordinary scan with `schedule_id` set, so the
queue, the agent, grounding checks, staff review and alerts all apply unchanged.

- Member schedules repeat a member's scan weekly, as scans of kind `scheduled`. They
  never use the member's scan quota. A run that finds nothing new for the member stays
  quiet; after `EMPTY_RUNS_TO_PAUSE` such runs in a row the schedule pauses itself and
  says so once. A schedule whose owner has not signed in for `INACTIVE_DAYS` pauses.
- Staff schedules run as the scheduled scans account (`run_as_staff`), as scans of kind
  `sweep`: the crawler pipeline first, then the agent with the schedule's focus. The
  catalogue sweep is the first of them (migration 0016).

Cost is capped by the `scheduled_scans` site settings: schedules per member, runs
started per hourly pass, and an optional daily token budget for scheduled runs.
"""

from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.orm import aliased

from api.auth.models import RefreshToken, User
from api.core.exceptions import BadRequestError, ConflictError, NotFoundError
from api.core.time import utcnow_naive
from api.opportunities.models import Opportunity, OpportunityCategory
from api.scans import models as m
from api.scans.service import check_sites, get_or_404, start_scan

MEMBER = "member"
STAFF = "staff"
#: Scan kind of a member schedule's runs; staff runs are sweeps.
SCHEDULED_KIND = "scheduled"
#: Members repeat weekly; staff choose daily, every three days or weekly.
MEMBER_INTERVAL_HOURS = 168
STAFF_INTERVAL_HOURS = (24, 72, 168)
EMPTY_RUNS_TO_PAUSE = 4
INACTIVE_DAYS = 60


def defaults() -> dict:
    return {"member_max": 3, "runs_per_hour": 10, "daily_token_budget": 0}


def config(values: dict) -> dict:
    """Stored `scheduled_scans` settings over the defaults."""
    return {**defaults(), **(values.get("scheduled_scans") or {})}


async def _config(session) -> dict:
    from api.editorial.service import get_settings

    return config(await get_settings(session))


async def run_as_staff(session) -> str | None:
    """The account staff schedules run as: the sweep account, else the first admin."""
    from api.opportunities.freshness import check_owner

    return await check_owner(session)


async def staff_schedules_active(session) -> bool:
    """Whether an unpaused staff schedule can run (it extracts crawler candidates)."""
    active = await session.scalar(
        select(func.count())
        .select_from(m.ScanSchedule)
        .where(m.ScanSchedule.audience == STAFF, m.ScanSchedule.paused.is_(False))
    )
    return bool(active) and await run_as_staff(session) is not None


# --- reading ----------------------------------------------------------------------


def _day_start(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def tokens_today(session, now: datetime | None = None) -> int:
    """Model tokens scheduled runs used since midnight UTC (Ghana time)."""
    since = _day_start(now or utcnow_naive())
    spent = await session.scalar(
        select(
            func.coalesce(
                func.sum(
                    func.coalesce(m.ScanTask.input_tokens, 0)
                    + func.coalesce(m.ScanTask.output_tokens, 0)
                ),
                0,
            )
        )
        .join(m.Scan, m.Scan.id == m.ScanTask.scan_id)
        .where(
            m.Scan.schedule_id.is_not(None),
            m.Scan.kind != "member",
            m.ScanTask.created_at >= since,
        )
    )
    return int(spent or 0)


def _visible():
    return (Opportunity.status == "published") | (
        m.ScanFind.created.is_(True) & (Opportunity.status == "in_review")
    )


async def run_counts(session, scan_ids: list[str]) -> dict[str, dict]:
    """{scan_id: {"new": listings added to the catalogue, "updated": refreshed}}."""
    if not scan_ids:
        return {}
    rows = await session.execute(
        select(
            m.ScanFind.scan_id,
            func.count().filter(m.ScanFind.created.is_(True)),
            func.count().filter(m.ScanFind.updated.is_(True)),
        )
        .join(Opportunity, Opportunity.id == m.ScanFind.opportunity_id)
        .where(m.ScanFind.scan_id.in_(scan_ids), _visible())
        .group_by(m.ScanFind.scan_id)
    )
    return {sid: {"new": new, "updated": updated} for sid, new, updated in rows.all()}


async def fresh_for_member(session, scan: m.Scan) -> int:
    """Listings this scan found that none of the member's earlier scans showed them."""
    earlier = aliased(m.ScanFind)
    seen = (
        select(1)
        .select_from(earlier)
        .join(m.Scan, m.Scan.id == earlier.scan_id)
        .where(
            m.Scan.user_id == scan.user_id,
            earlier.opportunity_id == m.ScanFind.opportunity_id,
            tuple_(earlier.found_at, earlier.scan_id)
            < tuple_(m.ScanFind.found_at, m.ScanFind.scan_id),
        )
        .exists()
    )
    return int(
        await session.scalar(
            select(func.count())
            .select_from(m.ScanFind)
            .join(Opportunity, Opportunity.id == m.ScanFind.opportunity_id)
            .where(m.ScanFind.scan_id == scan.id, _visible(), ~seen)
        )
        or 0
    )


async def schedule_out(session, row: m.ScanSchedule) -> dict:
    last = None
    if row.last_scan_id:
        scan = await session.get(m.Scan, row.last_scan_id)
        if scan is not None:
            counts = (await run_counts(session, [scan.id])).get(
                scan.id, {"new": 0, "updated": 0}
            )
            last = {
                "scan_id": scan.id,
                "status": scan.status,
                "created_at": scan.created_at,
                **counts,
            }
    return {
        "id": row.id,
        "audience": row.audience,
        "name": row.name,
        "categories": row.categories or [],
        "region": row.region,
        "focus": row.focus,
        "sites": row.sites or [],
        "interval_hours": row.interval_hours,
        "paused": row.paused,
        "pause_reason": row.pause_reason if row.paused else None,
        "next_run_at": None if row.paused else row.next_run_at,
        "last_run_at": row.last_run_at,
        "runs": row.runs,
        "last_run": last,
        "created_at": row.created_at,
    }


async def _rows(session, *where) -> list[m.ScanSchedule]:
    return list(
        (
            await session.execute(
                select(m.ScanSchedule)
                .where(*where)
                .order_by(m.ScanSchedule.created_at, m.ScanSchedule.id)
            )
        )
        .scalars()
        .all()
    )


# --- member schedules -------------------------------------------------------------


async def list_member(session, user_id: str) -> list[m.ScanSchedule]:
    return await _rows(
        session,
        m.ScanSchedule.audience == MEMBER,
        m.ScanSchedule.user_id == user_id,
    )


async def member_limit(session) -> int:
    return int((await _config(session))["member_max"])


async def _get_member(session, user_id: str, schedule_id: str) -> m.ScanSchedule:
    row = await session.get(m.ScanSchedule, schedule_id)
    if row is None or row.audience != MEMBER or row.user_id != user_id:
        raise NotFoundError("Schedule not found")
    return row


def _request_key(categories, region, focus, sites) -> tuple:
    from api.core.config import settings

    return (
        tuple(sorted(categories or [])),
        ((region or "").strip() or settings.opportunity_default_region).casefold(),
        (focus or "").strip(),
        tuple(sorted(sites or [])),
    )


async def ensure_can_repeat(
    session, user_id: str, *, categories, region, focus, sites
) -> None:
    """Raise unless the member may add a schedule for this request. Takes a lock
    held until the caller commits, so two requests cannot both pass."""
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext("scan-schedules:" + user_id)))
    )
    rows = await list_member(session, user_id)
    key = _request_key(categories, region, focus, sites)
    if any(_request_key(r.categories, r.region, r.focus, r.sites) == key for r in rows):
        raise ConflictError("This scan already repeats.")
    limit = await member_limit(session)
    if len(rows) >= limit:
        raise BadRequestError(
            f"You can repeat up to {limit} scans. Stop one to repeat another."
        )


async def repeat_scan(session, user_id: str, scan_id: str) -> m.ScanSchedule:
    """Repeat one of the member's own scans weekly. The scan counts as the first run."""
    scan = await get_or_404(session, user_id, scan_id)
    if scan.kind != "member":
        raise BadRequestError("Only scans you started can repeat.")
    await ensure_can_repeat(
        session,
        user_id,
        categories=scan.categories,
        region=scan.region,
        focus=scan.focus,
        sites=scan.sites,
    )
    now = utcnow_naive()
    row = m.ScanSchedule(
        audience=MEMBER,
        user_id=user_id,
        created_by=user_id,
        name="",
        categories=list(scan.categories or []),
        region=scan.region,
        focus=scan.focus or "",
        sites=list(scan.sites or []),
        interval_hours=MEMBER_INTERVAL_HOURS,
        paused=False,
        next_run_at=scan.created_at + timedelta(hours=MEMBER_INTERVAL_HOURS),
        last_run_at=scan.created_at,
        last_scan_id=scan.id,
        runs=0,
        empty_runs=0,
        touched_at=now,
        created_at=now,
    )
    session.add(row)
    await session.flush()
    scan.schedule_id = row.id
    await session.commit()
    return row


def _resume(row: m.ScanSchedule, now: datetime) -> None:
    row.paused = False
    row.pause_reason = None
    row.empty_runs = 0
    row.next_run_at = max(row.next_run_at, now)


async def update_member(
    session, user_id: str, schedule_id: str, values: dict
) -> m.ScanSchedule:
    row = await _get_member(session, user_id, schedule_id)
    now = utcnow_naive()
    if "focus" in values:
        row.focus = (values["focus"] or "").strip()
    if "sites" in values:
        row.sites = await check_sites(values["sites"] or [])
    if "paused" in values:
        if values["paused"]:
            row.paused = True
            row.pause_reason = None
        elif row.paused:
            _resume(row, now)
    row.touched_at = now
    await session.commit()
    return row


async def delete_member(session, user_id: str, schedule_id: str) -> None:
    row = await _get_member(session, user_id, schedule_id)
    await session.delete(row)
    await session.commit()


# --- staff schedules --------------------------------------------------------------


async def list_staff(session) -> list[m.ScanSchedule]:
    return await _rows(session, m.ScanSchedule.audience == STAFF)


async def _get_staff(session, schedule_id: str) -> m.ScanSchedule:
    row = await session.get(m.ScanSchedule, schedule_id)
    if row is None or row.audience != STAFF:
        raise NotFoundError("Schedule not found")
    return row


def _categories(values: list[str]) -> list[str]:
    chosen = set(values)
    ordered = [c.value for c in OpportunityCategory if c.value in chosen]
    if not ordered:
        raise BadRequestError("Choose at least one category.", field="categories")
    return ordered


def _interval(hours: int) -> int:
    if hours not in STAFF_INTERVAL_HOURS:
        raise BadRequestError(
            "Repeat daily, every 3 days or weekly.", field="interval_hours"
        )
    return hours


async def create_staff(session, staff_id: str, values: dict) -> m.ScanSchedule:
    now = utcnow_naive()
    row = m.ScanSchedule(
        audience=STAFF,
        user_id=None,
        created_by=staff_id,
        name=(values.get("name") or "").strip(),
        categories=_categories(values.get("categories") or []),
        region=(values.get("region") or "").strip(),
        focus=(values.get("focus") or "").strip(),
        sites=[],
        interval_hours=_interval(int(values.get("interval_hours") or 0)),
        paused=bool(values.get("paused", False)),
        # The first run starts on the next hourly pass.
        next_run_at=now,
        runs=0,
        empty_runs=0,
        touched_at=now,
        created_at=now,
    )
    session.add(row)
    await session.flush()
    return row


async def update_staff(session, schedule_id: str, values: dict) -> m.ScanSchedule:
    row = await _get_staff(session, schedule_id)
    now = utcnow_naive()
    if "name" in values:
        row.name = (values["name"] or "").strip()
    if "categories" in values:
        row.categories = _categories(values["categories"] or [])
    if "region" in values:
        row.region = (values["region"] or "").strip()
    if "focus" in values:
        row.focus = (values["focus"] or "").strip()
    if "interval_hours" in values:
        hours = _interval(int(values["interval_hours"]))
        if hours != row.interval_hours and row.last_run_at is not None:
            row.next_run_at = max(now, row.last_run_at + timedelta(hours=hours))
        row.interval_hours = hours
    if "paused" in values:
        if values["paused"]:
            row.paused = True
            row.pause_reason = None
        elif row.paused:
            _resume(row, now)
    row.touched_at = now
    await session.flush()
    return row


async def delete_staff(session, schedule_id: str) -> m.ScanSchedule:
    row = await _get_staff(session, schedule_id)
    await session.delete(row)
    await session.flush()
    return row


# --- running ----------------------------------------------------------------------


async def _last_active(session, row: m.ScanSchedule) -> datetime:
    signed_in = await session.scalar(
        select(func.max(RefreshToken.created_at)).where(
            RefreshToken.user_id == row.user_id
        )
    )
    return max(t for t in (signed_in, row.touched_at, row.created_at) if t is not None)


async def run_due(session, now: datetime | None = None) -> int:
    """Hourly: start the due schedules, within the caps. Returns runs started. Commits."""
    now = now or utcnow_naive()
    cfg = await _config(session)
    limit = int(cfg["runs_per_hour"])
    if limit <= 0:
        return 0
    budget = int(cfg["daily_token_budget"])
    if budget > 0 and await tokens_today(session, now) >= budget:
        return 0
    staff_owner = await run_as_staff(session)
    previous = aliased(m.Scan)
    running = (
        select(1)
        .select_from(previous)
        .where(
            previous.schedule_id == m.ScanSchedule.id,
            previous.status == "running",
        )
        .exists()
    )
    audiences = [MEMBER] + ([STAFF] if staff_owner else [])
    rows = list(
        (
            await session.execute(
                select(m.ScanSchedule)
                .outerjoin(User, User.id == m.ScanSchedule.user_id)
                .where(
                    m.ScanSchedule.paused.is_(False),
                    m.ScanSchedule.next_run_at <= now,
                    m.ScanSchedule.audience.in_(audiences),
                    or_(
                        m.ScanSchedule.audience == STAFF,
                        and_(User.id.is_not(None), User.disabled_at.is_(None)),
                    ),
                    ~running,
                )
                .order_by(m.ScanSchedule.next_run_at, m.ScanSchedule.id)
                .limit(limit)
                .with_for_update(skip_locked=True, of=m.ScanSchedule)
            )
        )
        .scalars()
        .all()
    )
    started = 0
    for row in rows:
        if row.audience == MEMBER:
            if await _last_active(session, row) < now - timedelta(days=INACTIVE_DAYS):
                row.paused = True
                row.pause_reason = "inactive"
                continue
            user_id, kind, sites = row.user_id, SCHEDULED_KIND, list(row.sites or [])
        else:
            user_id, kind, sites = staff_owner, "sweep", []
        assert user_id is not None
        scan = await start_scan(
            session,
            user_id,
            categories=list(row.categories or []),
            region=row.region,
            focus=row.focus,
            sites=sites,
            kind=kind,
            schedule_id=row.id,
            commit=False,
        )
        row.last_run_at = now
        row.last_scan_id = scan.id
        row.runs += 1
        # No catch-up after downtime: one run now, then the next slot.
        row.next_run_at = now + timedelta(hours=max(row.interval_hours, 1))
        started += 1
    await session.commit()
    return started


async def run_finished(session, scan: m.Scan) -> None:
    """After a scheduled run: track empty runs; pause a member's after too many."""
    if not scan.schedule_id or scan.kind == "member":
        return
    row = await session.get(m.ScanSchedule, scan.schedule_id)
    if row is None or row.last_scan_id != scan.id:
        return
    if row.audience == MEMBER:
        found = await fresh_for_member(session, scan)
    else:
        found = (await run_counts(session, [scan.id])).get(scan.id, {}).get("new", 0)
    if found:
        row.empty_runs = 0
        return
    row.empty_runs += 1
    if (
        row.audience == MEMBER
        and row.empty_runs >= EMPTY_RUNS_TO_PAUSE
        and not row.paused
    ):
        row.paused = True
        row.pause_reason = "empty"
        from api.notifications import events

        await events.schedule_paused(session, row, scan)
