"""When an index fact counts as stale, so refreshes re-check only what is old.

Admission cycles are checked monthly, and weekly once a deadline is within
two months, because that is when they change.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from api.core.time import utcnow_naive

STALE_AFTER: dict[str, timedelta] = {
    "faculty": timedelta(days=30),
    "works": timedelta(days=30),
    "programme": timedelta(days=365),
    "bio": timedelta(days=180),
    "cycle": timedelta(days=30),
}
#: A cycle whose deadline is this close is checked more often.
CYCLE_NEAR_DEADLINE = timedelta(days=60)
CYCLE_NEAR_STALE_AFTER = timedelta(days=7)


def stale_after(kind: str, *, deadline: date | None = None, today: date | None = None) -> timedelta:
    if kind == "cycle" and deadline is not None:
        today = today or utcnow_naive().date()
        if timedelta(0) <= deadline - today <= CYCLE_NEAR_DEADLINE:
            return CYCLE_NEAR_STALE_AFTER
    return STALE_AFTER[kind]


def is_stale(
    kind: str,
    fetched_at: datetime | None,
    *,
    deadline: date | None = None,
    now: datetime | None = None,
) -> bool:
    """True when the fact was never fetched or is older than its kind allows."""
    if fetched_at is None:
        return True
    now = now or utcnow_naive()
    return now - fetched_at > stale_after(kind, deadline=deadline, today=now.date())
