"""Clock helpers (naive UTC, matching the DB convention)."""

from datetime import UTC, datetime


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def duration_seconds(start: datetime | None, end: datetime | None) -> float | None:
    """Non-negative seconds between two timestamps, tz-normalized.

    ``end=None`` gives 0.0; ``start=None`` gives None."""
    if start is None:
        return None
    s = start.replace(tzinfo=None) if start.tzinfo else start
    raw = end if end is not None else start
    e = raw.replace(tzinfo=None) if raw.tzinfo else raw
    return max(0.0, (e - s).total_seconds())
