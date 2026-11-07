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
from api.core.exceptions import RateLimitError

# bucket -> [(max_calls, window_seconds), ...]; every window must allow.
LIMITS: dict[str, list[tuple[int, int]]] = {
    # File uploads: CVs and profile pictures.
    "upload": [(10, 60), (60, 3600)],
    # One chat turn (send or confirm) = one model loop.
    "chat": [(15, 60), (300, 3600)],
    # CV proposals stored for review (assistant or editor).
    "proposal": [(20, 60), (200, 3600)],
    # Anything that queues agent work: new runs, draft requests,
    # manually added schools/professors (each queues research).
    "agent_work": [(10, 60), (100, 3600)],
    # PDF exports: each fetches photos and renders a document.
    "export": [(6, 60), (60, 3600)],
    # Password-reset requests, keyed by the email asked about and by IP
    # (anonymous endpoint, so not per account).
    "reset_email": [(3, 900), (10, 86400)],
    "reset_ip": [(10, 900), (50, 86400)],
    # Settings > Notifications "Send a test notification".
    "test_notification": [(3, 60), (20, 3600)],
}

_LABEL = {
    "upload": "uploads",
    "chat": "chat messages",
    "proposal": "CV proposals",
    "agent_work": "research requests",
    "export": "PDF exports",
    "reset_email": "reset requests",
    "reset_ip": "reset requests",
    "test_notification": "test notifications",
}


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, bucket: str, key: str, now: float | None = None) -> float | None:
        """Record one call; return seconds to wait if over a limit (not counted), else None."""
        now = time.monotonic() if now is None else now
        windows = LIMITS[bucket]
        longest = max(w for _, w in windows)
        with self._lock:
            hits = self._hits[(bucket, key)]
            while hits and now - hits[0] >= longest:
                hits.popleft()
            wait = 0.0
            for limit, window in windows:
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
