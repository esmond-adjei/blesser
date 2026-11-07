"""HTTP for the keyless verification sources besides OpenAlex.

Per-source pacing (a request that would queue past
SOURCE_MAX_QUEUE_SECONDS is skipped) and a breaker: after a timeout, 5xx
or 429 the source is skipped for SOURCE_OUTAGE_SECONDS or its Retry-After,
so an outage costs one request, not one per task. Responses are cached in
process and in OpenAlex's Postgres store. Every failure is a
SourceUnavailable, which callers treat as "no answer".
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import time

import httpx

from api.core.config import settings
from api.core.ttlcache import TTLCache

log = logging.getLogger(__name__)


class SourceUnavailable(RuntimeError):
    """The source didn't answer (outage, throttled, busy, bad response)."""


_client: httpx.AsyncClient | None = None
#: source -> monotonic time its next request may start
_next_slot: dict[str, float] = {}
#: source -> monotonic time it is skipped until
_down: dict[str, float] = {}
_RESPONSES: TTLCache[dict] = TTLCache(1024, lambda: settings.source_cache_seconds)


def _user_agent() -> str:
    contact = settings.openalex_mailto.strip()
    return f"graduator (mailto:{contact})" if contact else "graduator"


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=settings.source_timeout_seconds,
            headers={"User-Agent": _user_agent()},
            follow_redirects=True,
            limits=httpx.Limits(max_connections=4, keepalive_expiry=30.0),
        )
    return _client


def reset() -> None:
    """Forget pacing, breakers and the client (tests)."""
    global _client
    _client = None
    _next_slot.clear()
    _down.clear()


def is_down(source: str) -> bool:
    until = _down.get(source)
    if until is not None and until <= time.monotonic():
        _down.pop(source, None)
        return False
    return until is not None


def _trip(source: str, seconds: float | None = None) -> None:
    wait = seconds if seconds and seconds > 0 else float(settings.source_outage_seconds)
    _down[source] = time.monotonic() + wait
    log.info("%s skipped for %.0fs after a failed request", source, wait)


async def _pace(source: str) -> None:
    """The slot is reserved synchronously, so concurrent tasks queue in order."""
    gap = max(0.0, float(settings.source_min_interval_seconds.get(source, 1.0)))
    now = time.monotonic()
    slot = max(now, _next_slot.get(source, 0.0))
    if slot - now > settings.source_max_queue_seconds:
        raise SourceUnavailable(f"{source} is busy")
    _next_slot[source] = slot + gap
    if slot > now:
        await asyncio.sleep(slot - now)


def _retry_after(resp: httpx.Response) -> float | None:
    try:
        return float(resp.headers.get("retry-after") or "")
    except ValueError:
        return None


async def request(
    source: str,
    url: str,
    *,
    params: dict | None = None,
    body: dict | None = None,
    text: bool = False,
    headers: dict | None = None,
) -> dict:
    """GET (POST with `body`) returning JSON, {"text"} with `text`, or {"items"}
    for a list. `headers` stay out of the cache key so API keys aren't stored."""
    from api.prospects import openalex

    key = f"{source}:{url}?" + json.dumps({"params": params, "body": body}, sort_keys=True)
    cached = _RESPONSES.get(key)
    if cached is not None:
        return copy.deepcopy(cached)
    stored = await openalex.stored_response(key)
    if stored is not None:
        _RESPONSES.put(key, copy.deepcopy(stored))
        return stored
    if is_down(source):
        raise SourceUnavailable(f"{source} is unavailable")
    await _pace(source)
    try:
        resp = await client().request(
            "POST" if body is not None else "GET", url, params=params, json=body, headers=headers
        )
    except httpx.HTTPError as exc:
        _trip(source)
        raise SourceUnavailable(f"{source}: {type(exc).__name__}") from exc
    if resp.status_code == 429 or resp.status_code >= 500:
        _trip(source, _retry_after(resp) if resp.status_code == 429 else None)
        raise SourceUnavailable(f"{source}: HTTP {resp.status_code}")
    if resp.status_code >= 400:
        raise SourceUnavailable(f"{source}: HTTP {resp.status_code}")
    try:
        data = {"text": resp.text} if text else resp.json()
    except ValueError as exc:
        raise SourceUnavailable(f"{source}: unreadable response") from exc
    if isinstance(data, list):
        data = {"items": data}
    if not isinstance(data, dict):
        raise SourceUnavailable(f"{source}: unexpected response")
    _RESPONSES.put(key, copy.deepcopy(data))
    await openalex.store_response(key, data, settings.openalex_db_cache_days)
    return data
