"""Run-scoped change notifications (Postgres LISTEN/NOTIFY).

pg_notify delivers only on commit, so emitting before the caller's commit is safe.
Duplicate wakes are harmless: the feed diffs state.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CHANNEL = "graduator_run_events"


async def _notify(session: AsyncSession, run_id: str, section: str) -> None:
    await session.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": CHANNEL, "payload": f"{run_id}:{section}"},
    )


async def notify_tasks(session: AsyncSession, run_id: str) -> None:
    await _notify(session, run_id, "tasks")


async def notify_work(session: AsyncSession, run_id: str) -> None:
    """Wake the worker; separate from notify_tasks because each wake costs a claim query."""
    await _notify(session, run_id, "work")


async def notify_candidates(session: AsyncSession, run_id: str) -> None:
    await _notify(session, run_id, "candidates")


async def notify_drafts(session: AsyncSession, run_id: str) -> None:
    await _notify(session, run_id, "drafts")


#: "work" wakes the worker; "notifications" (payload "<user_id>:notifications") the delivery loop.
SECTIONS = ("tasks", "candidates", "drafts", "work", "notifications")


def parse_payload(payload: object) -> tuple[str, str] | None:
    """(run_id, section), or None when the payload isn't ours; strict, since the sweep covers misses."""
    if not isinstance(payload, str):
        return None
    run_id, sep, section = payload.partition(":")
    if not sep or section not in SECTIONS:
        return None
    return run_id, section
