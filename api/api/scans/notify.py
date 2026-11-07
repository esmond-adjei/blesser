"""Postgres LISTEN/NOTIFY wakes: new work for the worker, new notifications for delivery.

pg_notify delivers only on commit, so emitting before the caller's commit is safe.
"""

from sqlalchemy import text

CHANNEL = "blesser_events"
SECTIONS = ("work", "notifications")


async def notify(session, key: str, section: str) -> None:
    await session.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": CHANNEL, "payload": f"{key}:{section}"},
    )


async def notify_work(session, scan_id: str) -> None:
    await notify(session, scan_id, "work")


def parse_payload(payload: object) -> tuple[str, str] | None:
    if not isinstance(payload, str):
        return None
    key, sep, section = payload.partition(":")
    if not sep or section not in SECTIONS:
        return None
    return key, section
