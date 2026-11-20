"""Scan lifecycle: start, read, cancel, delete, conclude. Callers own the commit unless noted."""

import json
from datetime import timedelta
from urllib.parse import urlsplit

from sqlalchemy import func, select, tuple_, update
from sqlalchemy.orm import aliased

from api.core.config import settings
from api.core.exceptions import NotFoundError
from api.core.time import utcnow_naive
from api.opportunities.models import Opportunity, OpportunityCategory
from api.scans import models as m
from api.scans.notify import notify_work

TASK_TYPE = "discover_opportunities"


async def start_scan(
    session,
    user_id: str,
    *,
    categories: list[str],
    region: str = "",
    focus: str = "",
    commit: bool = True,
) -> m.Scan:
    """Create the scan and queue one discovery task per category. Commits."""
    chosen = set(categories)
    ordered = [c.value for c in OpportunityCategory if c.value in chosen] or [
        c.value for c in OpportunityCategory
    ]
    scan = m.Scan(
        user_id=user_id,
        region=region.strip() or settings.opportunity_default_region,
        categories=ordered,
        focus=focus.strip(),
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


async def _added_counts(session, scan_ids: list[str]) -> dict[str, int]:
    if not scan_ids:
        return {}
    rows = await session.execute(
        select(Opportunity.scan_id, func.count())
        .where(Opportunity.scan_id.in_(scan_ids))
        .group_by(Opportunity.scan_id)
    )
    return dict(rows.all())


def _scan_out(scan: m.Scan, added: int, tasks: list[m.ScanTask] | None = None) -> dict:
    out = {
        "metrics": aggregate_metrics(tasks or []),
        "id": scan.id,
        "region": scan.region,
        "categories": scan.categories or [],
        "focus": scan.focus,
        "status": scan.status,
        "created_at": scan.created_at,
        "opportunities_added": added,
    }
    if tasks is not None:
        out["tasks"] = [task_out(t) for t in sorted(tasks, key=lambda t: t.created_at)]
        out.update(_timing(scan, tasks))
    return out


def _timing(scan: m.Scan, tasks: list[m.ScanTask]) -> dict:
    starts = [t.started_at for t in tasks if t.started_at]
    ends = [t.finished_at for t in tasks if t.finished_at]
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
    added = await _added_counts(session, [s.id for s in scans])
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
        out = _scan_out(scan, added.get(scan.id, 0))
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
        select(Opportunity, m.ScanFind.source_url, seen.label("seen"))
        .join(m.ScanFind, m.ScanFind.opportunity_id == Opportunity.id)
        .where(
            m.ScanFind.scan_id == scan.id,
            (Opportunity.status == "published")
            | ((Opportunity.scan_id == scan.id) & (Opportunity.status == "in_review")),
        )
        .order_by(m.ScanFind.found_at, Opportunity.id)
    )
    finds = []
    for opportunity, found_url, already_seen in rows:
        from_web = opportunity.scan_id == scan.id
        source_url, domain = _web_url(found_url if from_web else opportunity.source_url)
        official_url, _ = _web_url(opportunity.link)
        finds.append(
            {
                "opportunity_id": opportunity.id,
                "title": opportunity.title,
                "slug": opportunity.slug,
                "category": opportunity.category,
                "kind": opportunity.kind,
                "deadline_date": opportunity.deadline_date,
                "source": "web" if from_web else "catalog",
                "source_domain": domain if from_web else None,
                "official_url": official_url or source_url,
                "is_new": not already_seen,
                "in_review": opportunity.status == "in_review",
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
    added = await _added_counts(session, [scan.id])
    out = _scan_out(scan, added.get(scan.id, 0), list(tasks))
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
    left = {}
    for key, seconds in (("per_hour", 3600), ("per_day", 86400)):
        used = await session.scalar(
            select(func.count())
            .select_from(m.Scan)
            .where(m.Scan.user_id == user_id, m.Scan.created_at > now - timedelta(seconds=seconds))
        )
        left[key] = max(0, limits[key] - (used or 0))
    return {
        "enabled": settings.rate_limits_enabled,
        "per_hour": limits["per_hour"],
        "left_this_hour": left["per_hour"],
        "per_day": limits["per_day"],
        "left_today": left["per_day"],
    }
