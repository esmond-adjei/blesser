"""Per-account throttles for uploads and AI-backed endpoints.

In-process sliding windows (a burst and a sustained window per bucket), correct
for the single API process; `RateLimiter` is the seam for a shared store.
"""

import math
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends

from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.core.config import settings
from api.core.db import get_session
from api.core.exceptions import RateLimitError

# bucket -> [(max_calls, window_seconds), ...]; every window must allow.
LIMITS: dict[str, list[tuple[int, int]]] = {
    "kit_upload": [(20, 3600), (100, 86400)],
    "public_submit": [(5, 3600)],
    "public_report": [(10, 3600)],
    # Agent scans spend model tokens and search calls.
    "scan": [(3, 3600), (10, 86400)],
    # Community submissions to the catalogue.
    "submit": [(10, 3600), (30, 86400)],
    # Password-reset requests, keyed by the email asked about and by IP
    # (anonymous endpoint, so not per account).
    "reset_email": [(3, 900), (10, 86400)],
    "reset_ip": [(10, 900), (50, 86400)],
    # Settings > Notifications "Send a test notification".
    "test_notification": [(3, 60), (20, 3600)],
}

_LABEL = {
    "kit_upload": "document uploads",
    "public_submit": "submissions",
    "public_report": "reports",
    "scan": "scans",
    "submit": "submissions",
    "reset_email": "reset requests",
    "reset_ip": "reset requests",
    "test_notification": "test notifications",
}


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(
        self,
        bucket: str,
        key: str,
        now: float | None = None,
        *,
        windows: list[tuple[int, int]] | None = None,
    ) -> float | None:
        """Record one call; return seconds to wait if over a limit (not counted), else None."""
        now = time.monotonic() if now is None else now
        windows = LIMITS[bucket] if windows is None else windows
        longest = max(w for _, w in windows)
        with self._lock:
            hits = self._hits[(bucket, key)]
            while hits and now - hits[0] >= longest:
                hits.popleft()
            wait = 0.0
            for limit, window in windows:
                if limit <= 0:
                    return float(window)
                recent = [t for t in hits if now - t < window]
                if len(recent) >= limit:
                    wait = max(wait, window - (now - recent[-limit]))
            if wait > 0:
                return wait
            hits.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def _human(seconds: float) -> str:
    if seconds < 90:
        return f"{max(1, math.ceil(seconds))} seconds"
    return f"{math.ceil(seconds / 60)} minutes"


def enforce(bucket: str, user_id: str) -> None:
    """Count one call for this key (account id, email or IP), or raise 429."""
    if not settings.rate_limits_enabled:
        return
    wait = limiter.hit(bucket, user_id)
    if wait is not None:
        raise RateLimitError(
            f"Too many {_LABEL[bucket]} for now. Try again in {_human(wait)}.",
            retry_after=math.ceil(wait),
        )


def rate_limit(bucket: str):
    """Route dependency: throttle the signed-in account for one bucket."""
    if bucket not in LIMITS:  # pragma: no cover - programming error
        raise ValueError(f"Unknown rate-limit bucket {bucket!r}")

    async def dependency(
        current: auth_schemas.UserOut = Depends(get_current_user),
    ) -> None:
        enforce(bucket, current.id)

    return dependency


async def enforce_scan_limit(
    session=Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    if not settings.rate_limits_enabled:
        return
    from datetime import timedelta

    from sqlalchemy import func, select

    from api.core.time import utcnow_naive
    from api.editorial.service import get_settings
    from api.scans.models import Scan

    limits = (await get_settings(session))["member_scan_limits"]
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(f"member-scans:{current.id}")))
    )
    now = utcnow_naive()
    for key, seconds in (("per_hour", 3600), ("per_day", 86400)):
        count = await session.scalar(
            select(func.count())
            .select_from(Scan)
            .where(
                Scan.user_id == current.id,
                Scan.created_at > now - timedelta(seconds=seconds),
            )
        )
        if count >= limits[key]:
            raise RateLimitError(
                "Scan limit reached. Try again later.", retry_after=seconds
            )

    wait = limiter.hit(
        "member_scan",
        current.id,
        windows=[(limits["per_hour"], 3600), (limits["per_day"], 86400)],
    )
    if wait is not None:
        raise RateLimitError(
            "Scan limit reached. Try again later.", retry_after=math.ceil(wait)
        )
