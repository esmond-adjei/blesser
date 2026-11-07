"""Scan lifecycle: start, read, cancel, delete, conclude. Callers own the commit unless noted."""

import json
from datetime import timedelta

from sqlalchemy import func, select, update

from api.core.config import settings
from api.core.exceptions import NotFoundError
from api.core.time import utcnow_naive
from api.opportunities.models import Opportunity, OpportunityCategory
from api.scans import models as m
from api.scans.notify import notify_work

TASK_TYPE = "discover_opportunities"


async def start_scan(
    session, user_id: str, *, categories: list[str], region: str = "", focus: str = ""
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
            m.ScanTask(scan_id=scan.id, user_id=user_id, task_type=TASK_TYPE, target=f"category:{category}")
        )
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
            select(func.count()).select_from(m.ScanTask).where(
                m.ScanTask.scan_id == scan_id, m.ScanTask.status.in_(m.INFLIGHT)
            )
        )
    ).scalar() or 0
    if open_tasks == 0:
        scan.status = "done"
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
    return out


async def list_scans(session, user_id: str, limit: int = 50) -> list[dict]:
    scans = (
        await session.execute(
            select(m.Scan)
            .where(m.Scan.user_id == user_id)
            .order_by(m.Scan.created_at.desc(), m.Scan.id)
            .limit(limit)
        )
    ).scalars().all()
    added = await _added_counts(session, [s.id for s in scans])
    return [_scan_out(s, added.get(s.id, 0)) for s in scans]


async def scan_detail(session, user_id: str, scan_id: str) -> dict:
    scan = await get_or_404(session, user_id, scan_id)
    tasks = (
        await session.execute(select(m.ScanTask).where(m.ScanTask.scan_id == scan.id))
    ).scalars().all()
    added = await _added_counts(session, [scan.id])
    return _scan_out(scan, added.get(scan.id, 0), list(tasks))


async def cancel_scan(session, user_id: str, scan_id: str) -> dict:
    """Stop the scan: pending tasks are cancelled; running ones stop at their next turn."""
    scan = await get_or_404(session, user_id, scan_id)
    if scan.status == "running":
        scan.status = "cancelled"
        await session.execute(
            update(m.ScanTask)
            .where(m.ScanTask.scan_id == scan.id, m.ScanTask.status == m.TaskStatus.pending)
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
