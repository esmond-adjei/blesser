"""Scheduled listing checks: keep published listings honest and catch new cycles of closed ones.

Every pass the worker claims a few listings that are due, most urgent first:

1. Published, closing within `closing_days`, and not confirmed for `closing_recheck_days`.
2. Published with no deadline (or rolling) and not confirmed for `recheck_days`.
3. Archived in the last year and not looked at for `cycle_days`: schemes often reopen a
   new cycle on the same page.

"Confirmed" is `verified_at` (falling back to `created_at`). Each claim stamps `checked_at`,
so a listing whose check fails is retried a day later rather than every pass.

A check first reads the source page through the shared page cache (no model call):

- Gone (404 or 410) or redirected to a homepage: the listing goes to staff review with
  `review_reason = source_changed`.
- Unchanged since the facts were last confirmed (same content hash): `verified_at` is
  stamped.
- Every deadline on the page has passed: an undated or rolling listing is archived; a
  dated one whose page disagrees goes to review.
- Changed: a `reverify_opportunity` agent task re-reads the page and saves the current
  facts, within `max_agent_checks` a day. For an archived listing this happens only when
  the page shows a deadline ahead or rolling applications; the save then reopens it.

Undated and rolling listings that nothing has confirmed for `stale_days` are archived by
the daily archive pass (archive.py), so an unreachable page cannot keep a listing open
forever.
"""

from datetime import timedelta
from urllib.parse import urlsplit

from sqlalchemy import and_, case, func, or_, select

from api.auth import models as auth_models
from api.core.config import settings
from api.core.time import utcnow_naive
from api.editorial.service import defaults, get_settings
from api.opportunities.crawl_models import PageCache
from api.opportunities.models import Opportunity, OpportunityStatus
from api.opportunities.page_cache import get_page
from api.opportunities.page_content import (
    Page,
    expired,
    normalized_url,
    shows_open_cycle,
)
from api.scans import models as scan_models

#: Scan focus that marks the scans these checks create (no "scan finished" notification).
CHECK_FOCUS = "Scheduled listing checks"
#: A failed or inconclusive check is retried after this long.
RETRY_AFTER = timedelta(hours=24)
#: Archived listings are watched for a new cycle for this long after their deadline.
CYCLE_WINDOW = timedelta(days=400)
#: How often the worker runs a pass.
INTERVAL_SECONDS = 900

PUBLISHED = OpportunityStatus.published.value
ARCHIVED = OpportunityStatus.archived.value
REVIEW = OpportunityStatus.in_review.value


def config(values: dict) -> dict:
    """Stored `freshness` settings over the defaults, so a partial row still works."""
    return {**defaults()["freshness"], **(values.get("freshness") or {})}


def _confirmed():
    return func.coalesce(Opportunity.verified_at, Opportunity.created_at)


def _due_clauses(cfg: dict, now):
    today = now.date()
    closing = and_(
        Opportunity.status == PUBLISHED,
        Opportunity.rolling.is_(False),
        Opportunity.deadline_date >= today,
        Opportunity.deadline_date <= today + timedelta(days=cfg["closing_days"]),
        _confirmed() < now - timedelta(days=cfg["closing_recheck_days"]),
    )
    undated = and_(
        Opportunity.status == PUBLISHED,
        or_(Opportunity.deadline_date.is_(None), Opportunity.rolling.is_(True)),
        _confirmed() < now - timedelta(days=cfg["recheck_days"]),
    )
    cycle = and_(
        Opportunity.status == ARCHIVED,
        Opportunity.source_url != "",
        or_(
            Opportunity.deadline_date.is_(None),
            Opportunity.deadline_date >= today - CYCLE_WINDOW,
        ),
        or_(
            Opportunity.checked_at.is_(None),
            Opportunity.checked_at < now - timedelta(days=cfg["cycle_days"]),
        ),
    )
    return closing, undated, cycle


async def claim_due(session, cfg: dict, now) -> list[Opportunity]:
    """Claim up to `max_checks` due listings by stamping `checked_at`; safe across workers."""
    if cfg["max_checks"] <= 0:
        return []
    closing, undated, cycle = _due_clauses(cfg, now)
    in_flight = select(scan_models.ScanTask.target).where(
        scan_models.ScanTask.task_type == "reverify_opportunity",
        scan_models.ScanTask.status.in_(scan_models.INFLIGHT),
        scan_models.ScanTask.target.is_not(None),
    )
    rows = (
        (
            await session.execute(
                select(Opportunity)
                .where(
                    or_(closing, undated, cycle),
                    or_(Opportunity.source_url != "", Opportunity.link != ""),
                    or_(
                        Opportunity.checked_at.is_(None),
                        Opportunity.checked_at < now - RETRY_AFTER,
                    ),
                    Opportunity.id.not_in(in_flight),
                )
                .order_by(
                    case((closing, 0), (undated, 1), else_=2),
                    _confirmed(),
                    Opportunity.id,
                )
                .limit(cfg["max_checks"])
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.checked_at = now
    await session.commit()
    return list(rows)


def moved_to_homepage(url: str, page: Page) -> bool:
    final = page.metadata.get("final_url")
    if not final:
        return False
    before, after = urlsplit(normalized_url(url)), urlsplit(normalized_url(final))
    return before.path not in ("", "/") and after.path in ("", "/")


def read_outcome(row: Opportunity, page: Page, today) -> str:
    """What the source page says, without a model: missing, moved, unreachable,
    unchanged, closed, open (archived only: a new cycle is advertised) or changed."""
    if page.error:
        return "missing" if page.error in ("http_404", "http_410") else "unreachable"
    if moved_to_homepage(row.source_url or row.link, page):
        return "moved"
    if row.source_hash and page.content_hash == row.source_hash:
        return "unchanged"
    if expired(page.text, page.metadata, today):
        return "closed"
    if row.status == ARCHIVED:
        return "open" if shows_open_cycle(page.text, page.metadata, today) else "closed"
    return "changed"


async def check_owner(session) -> str | None:
    """The account that owns agent checks: the sweep account, else the first admin."""
    from api.opportunities.sweep import sweep_user_id

    if owner := await sweep_user_id(session):
        return owner
    return (
        await session.execute(
            select(auth_models.User.id)
            .where(
                auth_models.User.role == "admin",
                auth_models.User.disabled_at.is_(None),
            )
            .order_by(auth_models.User.created_at, auth_models.User.id)
            .limit(1)
        )
    ).scalar_one_or_none()


async def agent_checks_today(session, now) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(scan_models.ScanTask)
            .join(scan_models.Scan, scan_models.Scan.id == scan_models.ScanTask.scan_id)
            .where(
                scan_models.Scan.focus == CHECK_FOCUS,
                scan_models.ScanTask.created_at >= now - timedelta(days=1),
            )
        )
    ).scalar_one()


class AgentQueue:
    """Queues agent re-checks into one scan per pass, within the daily budget."""

    def __init__(self, session, cfg: dict, now):
        self.session, self.cfg, self.now = session, cfg, now
        self.scan: scan_models.Scan | None = None
        self.owner: str | None = None
        self.remaining: int | None = None

    async def add(self, row: Opportunity) -> bool:
        if self.remaining is None:
            self.remaining = max(
                0,
                self.cfg["max_agent_checks"]
                - await agent_checks_today(self.session, self.now),
            )
            self.owner = await check_owner(self.session) if self.remaining else None
        if not self.remaining or self.owner is None:
            return False
        if self.scan is None:
            self.scan = scan_models.Scan(
                user_id=self.owner,
                region=settings.opportunity_default_region,
                categories=[],
                focus=CHECK_FOCUS,
                status="running",
            )
            self.session.add(self.scan)
            await self.session.flush()
        if row.category not in self.scan.categories:
            self.scan.categories = [*self.scan.categories, row.category]
        self.session.add(
            scan_models.ScanTask(
                scan_id=self.scan.id,
                user_id=self.owner,
                task_type="reverify_opportunity",
                target=row.id,
                metrics={"scheduled_check": True},
            )
        )
        self.remaining -= 1
        return True

    async def notify(self) -> None:
        if self.scan is not None:
            from api.scans.notify import notify_work

            await notify_work(self.session, self.scan.id)


async def apply_outcome(
    session, row: Opportunity, page: Page, outcome: str, queue: AgentQueue, values
) -> str:
    """Act on a read outcome; returns what was recorded on the listing."""
    now = queue.now
    today = now.date()
    if outcome in ("unchanged", "closed", "moved"):
        # Settled for this content; "changed" and "open" wait for the agent's verdict.
        row.source_hash = page.content_hash
    if row.status == ARCHIVED:
        if outcome == "open" and await queue.add(row):
            outcome = "queued"
        return outcome
    if outcome in ("missing", "moved"):
        row.status, row.review_reason = REVIEW, "source_changed"
    elif outcome == "unchanged":
        row.verified_at = now
    elif outcome == "closed":
        undated = row.deadline_date is None or row.rolling
        if undated and values["auto_archive"]:
            row.status = ARCHIVED
        elif row.deadline_date is None or row.deadline_date >= today or row.rolling:
            # The page says it closed but the listing says it is open.
            row.status, row.review_reason = REVIEW, "source_changed"
    elif outcome == "changed":
        outcome = "queued" if await queue.add(row) else "changed"
    return outcome


async def run_checks(session, *, now=None) -> dict:
    """One pass: claim due listings, read their pages, act. Returns outcome counts."""
    now = now or utcnow_naive()
    values = await get_settings(session)
    cfg = config(values)
    rows = await claim_due(session, cfg, now)
    counts: dict[str, int] = {}
    queue = AgentQueue(session, cfg, now)
    for claimed in rows:
        page = await get_page(claimed.source_url or claimed.link)
        row = await session.get(Opportunity, claimed.id, with_for_update=True)
        if row is None:
            continue
        outcome = read_outcome(row, page, now.date())
        outcome = await apply_outcome(session, row, page, outcome, queue, values)
        row.check_outcome = outcome
        counts[outcome] = counts.get(outcome, 0) + 1
        await session.commit()
    await queue.notify()
    await session.commit()
    return counts


async def record_agent_check(session, task, started) -> None:
    """After a `reverify_opportunity` task: note whether the source still confirmed it.

    A scheduled check that could not confirm a published listing sends it to review; a
    staff-requested one only records the outcome, since staff are already looking.
    """
    row = await session.get(Opportunity, task.target)
    if row is None:
        return
    scheduled = bool((task.metrics or {}).get("scheduled_check"))
    cached = await session.get(PageCache, normalized_url(row.source_url or row.link))
    page_hash = cached.content_hash if cached is not None and not cached.error else ""
    if row.verified_at is not None and row.verified_at >= started:
        row.source_hash = page_hash
        if row.check_outcome != "reopened":
            row.check_outcome = "verified"
    elif row.status == ARCHIVED:
        row.source_hash = page_hash
        row.check_outcome = "closed"
    else:
        row.check_outcome = "unconfirmed"
        if scheduled and row.status == PUBLISHED:
            row.status, row.review_reason = REVIEW, "source_changed"
    row.checked_at = utcnow_naive()
    await session.flush()
