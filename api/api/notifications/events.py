"""Notification event sites: one function per kind of event.

Each runs inside the causing change's transaction and never commits. Text goes
through the browser vendor's push service, so keep it to titles and counts.
"""

from sqlalchemy import func, select

from api.core.time import utcnow_naive
from api.notifications.service import notify
from api.scans import models as scan_models


async def scan_finished(session, scan: scan_models.Scan) -> bool:
    """Keyed on the task count, so a re-run scan announces again."""
    from api.scans.service import find_counts

    tasks = (
        await session.execute(
            select(func.count())
            .select_from(scan_models.ScanTask)
            .where(scan_models.ScanTask.scan_id == scan.id)
        )
    ).scalar() or 0
    found, added = (await find_counts(session, [scan.id])).get(scan.id, (0, 0))
    if scan.kind == "sources" and found == 0:
        # A scheduled check of the member's sources that found nothing is not news.
        return False
    return await notify(
        session,
        user_id=scan.user_id,
        kind="scan_finished",
        title="Scan finished",
        body=scan_summary(scan.region, found, added),
        link=f"/scans/{scan.id}",
        entity_id=scan.id,
        dedupe_key=f"scan:{scan.id}:done:{tasks}",
    )


def scan_summary(region: str, found: int, added: int) -> str:
    if found == 0:
        return f"Your opportunity scan in {region} didn't find anything that fits yet."
    noun = "opportunity" if found == 1 else "opportunities"
    return (
        f"Your opportunity scan in {region} found {found} {noun} for you, "
        f"{added} new to Blesser."
    )


async def scan_attention(session, scan: scan_models.Scan) -> bool:
    """A task failed for good. At most one a day per scan."""
    day = utcnow_naive().date().isoformat()
    return await notify(
        session,
        user_id=scan.user_id,
        kind="scan_attention",
        title="Scan needs attention",
        body=f"A task in your opportunity scan in {scan.region} failed after its retries.",
        link=f"/scans/{scan.id}",
        entity_id=scan.id,
        dedupe_key=f"scan:{scan.id}:attention:{day}",
    )
