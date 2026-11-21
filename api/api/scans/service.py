"""Scan lifecycle: start, read, cancel, delete, conclude. Callers own the commit unless noted."""

import json
from datetime import timedelta
from urllib.parse import urlsplit

from sqlalchemy import func, select, tuple_, update
from sqlalchemy.orm import aliased

from api.core.config import settings
from api.core.exceptions import ConflictError, NotFoundError
from api.core.time import utcnow_naive
from api.opportunities.models import Opportunity, OpportunityCategory
from api.scans import models as m
from api.scans.notify import notify_work

TASK_TYPE = "discover_opportunities"
#: Sites a member may ask one scan to read first.
MAX_SCAN_SITES = 5


async def check_sites(raw: list[str]) -> list[str]:
    """Clean the member's sites: https assumed, public addresses only, no repeats.

    The egress guard runs again on every fetch (redirects included); this check
    turns a bad address into a clear error before the scan starts.
    """
    import httpx

    from api.core import egress
    from api.core.exceptions import BadRequestError
    from api.opportunities.page_content import normalized_url

    sites: list[str] = []
    seen: set[str] = set()
    for value in raw:
        site = value.strip()
        if not site:
            continue
        if "://" not in site:
            site = "https://" + site
        try:
            await egress.check_url(site)
        except httpx.ConnectError as exc:
            raise BadRequestError(
                f"We couldn't find {value.strip()}. Check the address.", field="sites"
            ) from exc
        except (egress.EgressBlocked, httpx.InvalidURL, ValueError) as exc:
            raise BadRequestError(
                f"{value.strip()} isn't a public web address.", field="sites"
            ) from exc
        key = normalized_url(site)
        if key not in seen:
            seen.add(key)
            sites.append(site)
    if len(sites) > MAX_SCAN_SITES:
        raise BadRequestError(
            f"Add at most {MAX_SCAN_SITES} sites to one scan.", field="sites"
        )
    return sites


KIND_PLURALS = {
    "grant": "grants",
    "fellowship": "fellowships",
    "scholarship": "scholarships",
    "accelerator": "accelerators",
    "incubator": "incubators",
    "competition": "competitions",
    "internship": "internships",
    "call_for_proposals": "calls for proposals",
    "training": "training",
    "conference": "conferences",
    "job": "jobs",
}
_KIND_WORDS = {
    "scholarship": ("scholarship", "bursar", "tuition"),
    "fellowship": ("fellowship",),
    "grant": ("grant", "funding", "seed fund"),
    "job": (" job", "jobs", "hiring", "career", "vacanc", "engineer role"),
    "internship": ("internship", "intern "),
    "accelerator": ("accelerator",),
    "incubator": ("incubat",),
    "competition": ("competition", "challenge", "prize", "hackathon"),
    "conference": ("conference", "summit"),
    "training": ("training", "bootcamp", "course"),
    "call_for_proposals": ("call for proposals", "proposals"),
}


def scan_kinds(kinds, focus: str = "") -> list[str]:
    """The listing types a scan is for: the ones picked, else any its focus names."""
    if kinds:
        return list(kinds)
    text = f" {(focus or '').casefold()} "
    return [k for k, words in _KIND_WORDS.items() if any(w in text for w in words)][:3]


def kinds_phrase(kinds) -> str:
    words = [KIND_PLURALS.get(k, k.replace("_", " ")) for k in kinds]
    return words[0] if len(words) < 2 else f"{', '.join(words[:-1])} and {words[-1]}"


async def start_scan(
    session,
    user_id: str,
    *,
    categories: list[str],
    region: str = "",
    focus: str = "",
    sites: list[str] | None = None,
    kinds: list[str] | None = None,
    kind: str = "member",
    schedule_id: str | None = None,
    commit: bool = True,
) -> m.Scan:
    """Create the scan and queue one discovery task per category. Commits.

    `sites` must already be checked (`check_sites`): public http(s) addresses only.
    """
    chosen = set(categories)
    ordered = [c.value for c in OpportunityCategory if c.value in chosen] or [
        c.value for c in OpportunityCategory
    ]
    scan = m.Scan(
        user_id=user_id,
        region=region.strip() or settings.opportunity_default_region,
        categories=ordered,
        focus=focus.strip(),
        kinds=list(dict.fromkeys(kinds or [])),
        kind=kind,
        sites=list(sites or []),
        schedule_id=schedule_id,
        status="running",
    )
    session.add(scan)
    await session.flush()
    for category in ordered:
        session.add(
            m.ScanTask(
                scan_id=scan.id,
                user_id=user_id,
                task_type=TASK_TYPE,
                target=f"category:{category}",
            )
        )
    await notify_work(session, scan.id)
    if commit:
        await session.commit()
    return scan


def _tried(tasks, limit: int = 15) -> dict[str, list[str]]:
    """What earlier runs searched for and read, newest last, so a follow-up can avoid it."""
    searches, pages = {}, {}
    for task in sorted(tasks, key=lambda t: t.created_at):
        for event in _parse_log(task.log):
            args = event.get("input") or {}
            if event.get("tool") == "search_web" and args.get("query"):
                searches[args["query"]] = None
            elif event.get("tool") == "fetch_page" and args.get("url"):
                pages[args["url"]] = None
    return {"searches": list(searches)[-limit:], "pages": list(pages)[-limit:]}


async def steer_scan(session, user_id: str, scan_id: str, prompt: str) -> m.Scan:
    """Queue a follow-up run on a finished scan, steered by what the member said."""
    scan = await get_or_404(session, user_id, scan_id)
    if scan.kind not in ("member", "scheduled"):
        raise ConflictError("This scan can't be steered.")
    if scan.status == "running":
        raise ConflictError(
            "Wait for this scan to finish, or stop it, before steering it."
        )
    earlier = (
        (await session.execute(select(m.ScanTask).where(m.ScanTask.scan_id == scan.id)))
        .scalars()
        .all()
    )
    tried = _tried(earlier)
    for category in scan.categories:
        session.add(
            m.ScanTask(
                scan_id=scan.id,
                user_id=user_id,
                task_type=TASK_TYPE,
                target=f"category:{category}",
                metrics={
                    "steer": prompt.strip(),
                    "pipeline_complete": True,
                    **({"tried": tried} if tried["searches"] or tried["pages"] else {}),
                },
            )
        )
    scan.status = "running"
    await session.flush()
    await notify_work(session, scan.id)
    await session.commit()
    return scan


async def note_tasks_drained(session, scan_id: str) -> None:
    """Flip a running scan to done once no task is open; the only way into done."""
    scan = await session.get(m.Scan, scan_id)
    if scan is None or scan.status != "running":
        return
    open_tasks = (
        await session.execute(
            select(func.count())
            .select_from(m.ScanTask)
            .where(m.ScanTask.scan_id == scan_id, m.ScanTask.status.in_(m.INFLIGHT))
        )
    ).scalar() or 0
    if open_tasks == 0:
        scan.status = "done"
        from api.opportunities.freshness import CHECK_FOCUS

        if scan.focus == CHECK_FOCUS:
            # Scheduled checks report through the listings themselves, not a notification.
            return
        from api.notifications import events
        from api.scans.schedules import run_finished
        from api.scans.sources import record_finds

        await record_finds(session, scan)
        await run_finished(session, scan)
        await events.scan_finished(session, scan)


async def get_or_404(session, user_id: str, scan_id: str) -> m.Scan:
    scan = await session.get(m.Scan, scan_id)
    if scan is None or scan.user_id != user_id:
        raise NotFoundError("Scan not found")
    return scan


def _parse_log(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return value if isinstance(value, list) else []


def task_out(task: m.ScanTask) -> dict:
    return {
        "id": task.id,
        "metrics": task.metrics or {},
        "task_type": task.task_type,
        "target": task.target,
        "status": m.status_str(task.status),
        "error": task.error,
        "final_text": task.final_text,
        "turns": task.turns,
        "log": _parse_log(task.log),
        "input_tokens": task.input_tokens,
        "output_tokens": task.output_tokens,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
    }


def _visible_find():
    """Finds a member may see: listings this scan newly added, whether or not they've
    been reviewed. Listings already in the catalogue are on their feed, so a scan doesn't list them."""
    return m.ScanFind.created.is_(True) & Opportunity.status.in_(
        ("published", "in_review", "draft")
    )


async def find_counts(session, scan_ids: list[str]) -> dict[str, tuple[int, int]]:
    """{scan_id: (listings found for the member, of which new to the catalogue)}."""
    if not scan_ids:
        return {}
    rows = await session.execute(
        select(
            m.ScanFind.scan_id,
            func.count(),
            func.count().filter(m.ScanFind.created.is_(True)),
        )
        .join(Opportunity, Opportunity.id == m.ScanFind.opportunity_id)
        .where(m.ScanFind.scan_id.in_(scan_ids), _visible_find())
        .group_by(m.ScanFind.scan_id)
    )
    return {scan_id: (found, new) for scan_id, found, new in rows.all()}


def _scan_out(
    scan: m.Scan,
    counts: tuple[int, int],
    tasks: list[m.ScanTask] | None = None,
    updated: int = 0,
) -> dict:
    found, added = counts
    out = {
        "metrics": aggregate_metrics(tasks or []),
        "id": scan.id,
        "region": scan.region,
        "categories": scan.categories or [],
        "focus": scan.focus,
        "kinds": scan.kinds or [],
        "sites": scan.sites or [],
        "kind": scan.kind,
        "status": scan.status,
        "created_at": scan.created_at,
        "opportunities_found": found,
        "opportunities_added": added,
        "opportunities_updated": updated,
        "schedule_id": scan.schedule_id,
    }
    if tasks is not None:
        out["tasks"] = [task_out(t) for t in sorted(tasks, key=lambda t: t.created_at)]
        out.update(_timing(scan, tasks))
    return out


RUN_WINDOW = timedelta(seconds=5)


def latest_run(tasks: list[m.ScanTask]) -> list[m.ScanTask]:
    """The tasks queued together last: a retry or a steer starts a new run on the same scan."""
    if not tasks:
        return []
    newest = max(t.created_at for t in tasks)
    return [t for t in tasks if t.created_at >= newest - RUN_WINDOW]


def _timing(scan: m.Scan, tasks: list[m.ScanTask]) -> dict:
    run = latest_run(tasks)
    starts = [t.started_at or t.created_at for t in run]
    ends = [t.finished_at for t in run if t.finished_at]
    finished = max(ends) if ends and m.status_str(scan.status) != "running" else None
    return {"started_at": min(starts) if starts else None, "finished_at": finished}


def aggregate_metrics(tasks) -> dict:
    out = {
        "candidates_found": 0,
        "candidates_considered": 0,
        "extracted": 0,
        "saved": 0,
        "model_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "duration_seconds": 0,
        "triaged_out": {},
        "sources": {},
    }
    for task in tasks:
        metrics = task.metrics or {}
        for key in out.keys() - {"triaged_out", "sources"}:
            out[key] += metrics.get(key, 0)
        for reason, count in metrics.get("triaged_out", {}).items():
            out["triaged_out"][reason] = out["triaged_out"].get(reason, 0) + count
        out["sources"].update(metrics.get("sources", {}))
    return out


async def list_scans(session, user_id: str, limit: int = 50) -> list[dict]:
    scans = (
        (
            await session.execute(
                select(m.Scan)
                .where(m.Scan.user_id == user_id)
                .order_by(m.Scan.created_at.desc(), m.Scan.id)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    counts = await find_counts(session, [s.id for s in scans])
    from api.scans.schedules import run_counts

    refreshed = await run_counts(session, [s.id for s in scans])
    tasks = (
        (
            await session.execute(
                select(m.ScanTask).where(m.ScanTask.scan_id.in_([s.id for s in scans]))
            )
        )
        .scalars()
        .all()
    )
    result = []
    for scan in scans:
        out = _scan_out(
            scan,
            counts.get(scan.id, (0, 0)),
            updated=refreshed.get(scan.id, {}).get("updated", 0),
        )
        mine = [t for t in tasks if t.scan_id == scan.id]
        out["metrics"] = aggregate_metrics(mine)
        out.update(_timing(scan, mine))
        result.append(out)
    return result


def _web_url(url: str | None) -> tuple[str | None, str | None]:
    if url:
        try:
            parsed = urlsplit(url)
            if parsed.scheme in {"http", "https"} and parsed.hostname:
                return url, parsed.hostname.removeprefix("www.")
        except ValueError:
            pass
    return None, None


async def _scan_finds(session, scan: m.Scan) -> list[dict]:
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
    rows = await session.execute(
        select(
            Opportunity, m.ScanFind.source_url, m.ScanFind.created, seen.label("seen")
        )
        .join(m.ScanFind, m.ScanFind.opportunity_id == Opportunity.id)
        .where(m.ScanFind.scan_id == scan.id, _visible_find())
        .order_by(m.ScanFind.created.desc(), m.ScanFind.found_at, Opportunity.id)
    )
    finds = []
    for opportunity, found_url, created, already_seen in rows:
        source_url, domain = _web_url(found_url if created else opportunity.source_url)
        official_url, _ = _web_url(opportunity.link)
        finds.append(
            {
                "opportunity_id": opportunity.id,
                "title": opportunity.title,
                "slug": opportunity.slug,
                "category": opportunity.category,
                "kind": opportunity.kind,
                "deadline_date": opportunity.deadline_date,
                "source": "web" if created else "catalog",
                "source_domain": domain if created else None,
                "official_url": official_url or source_url,
                "is_new": not already_seen,
                "in_review": opportunity.status in ("in_review", "draft"),
            }
        )
    return finds


async def scan_detail(session, user_id: str, scan_id: str) -> dict:
    scan = await get_or_404(session, user_id, scan_id)
    tasks = (
        (await session.execute(select(m.ScanTask).where(m.ScanTask.scan_id == scan.id)))
        .scalars()
        .all()
    )
    counts = await find_counts(session, [scan.id])
    from api.scans.schedules import run_counts

    refreshed = (await run_counts(session, [scan.id])).get(scan.id, {})
    out = _scan_out(
        scan,
        counts.get(scan.id, (0, 0)),
        list(tasks),
        updated=refreshed.get("updated", 0),
    )
    out["finds"] = await _scan_finds(session, scan)
    return out


async def cancel_scan(session, user_id: str, scan_id: str) -> dict:
    """Stop the scan: pending tasks are cancelled; running ones stop at their next turn."""
    scan = await get_or_404(session, user_id, scan_id)
    if scan.status == "running":
        scan.status = "cancelled"
        await session.execute(
            update(m.ScanTask)
            .where(
                m.ScanTask.scan_id == scan.id, m.ScanTask.status == m.TaskStatus.pending
            )
            .values(status=m.TaskStatus.cancelled, finished_at=utcnow_naive())
            .execution_options(synchronize_session=False)
        )
        await session.commit()
    return await scan_detail(session, user_id, scan_id)


async def delete_scan(session, user_id: str, scan_id: str) -> dict:
    """Removes the scan and its traces; the opportunities it found stay in the catalogue."""
    scan = await get_or_404(session, user_id, scan_id)
    await session.delete(scan)
    await session.commit()
    return {"status": "deleted"}


async def prune_traces(session) -> int:
    """Drop old traces and checkpoints (they hold fetched pages) after TRACE_RETENTION_DAYS."""
    days = settings.trace_retention_days
    if days <= 0:
        return 0
    cutoff = utcnow_naive() - timedelta(days=days)
    result = await session.execute(
        update(m.ScanTask)
        .where(
            m.ScanTask.finished_at.is_not(None),
            m.ScanTask.finished_at < cutoff,
            (m.ScanTask.log.is_not(None)) | (m.ScanTask.messages_json.is_not(None)),
        )
        .values(log=None, messages_json=None)
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    return result.rowcount or 0


async def scan_allowance(session, user_id: str) -> dict:
    from datetime import timedelta

    from api.core.config import settings
    from api.editorial.service import get_settings

    limits = (await get_settings(session))["member_scan_limits"]
    now = utcnow_naive()
    left, frees = {}, []
    for key, seconds in (("per_hour", 3600), ("per_day", 86400)):
        window = timedelta(seconds=seconds)
        started = (
            (
                await session.execute(
                    select(m.Scan.created_at)
                    .where(
                        m.Scan.user_id == user_id,
                        m.Scan.kind == "member",
                        m.Scan.created_at > now - window,
                    )
                    .order_by(m.Scan.created_at)
                )
            )
            .scalars()
            .all()
        )
        left[key] = max(0, limits[key] - len(started))
        if not left[key] and started and limits[key] > 0:
            # A slot frees when the scan that fills the limit leaves the window.
            frees.append(started[len(started) - limits[key]] + window)
    return {
        "next_at": max(frees) if frees else None,
        "enabled": settings.rate_limits_enabled,
        "per_hour": limits["per_hour"],
        "left_this_hour": left["per_hour"],
        "per_day": limits["per_day"],
        "left_today": left["per_day"],
    }
