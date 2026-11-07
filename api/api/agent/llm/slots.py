"""Per-backend caps on concurrent model calls, per worker process.

A local server (Ollama) queues excess requests until they time out and retry into the
same queue; waiting here instead doesn't count against the call deadline.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

from api.core.config import settings

# Per event loop: a Semaphore binds to its loop, and tests use a fresh loop per case.
_loop: asyncio.AbstractEventLoop | None = None
_slots: dict[tuple[str, str], asyncio.Semaphore] = {}


def backend_key(provider) -> tuple[str, str]:
    """(provider name, base URL): one server's slots are shared across models and accounts."""
    name = (getattr(provider, "name", "") or type(provider).__name__).lower()
    return name, (getattr(provider, "base_url", None) or "").rstrip("/")


def backend_limit(provider) -> int:
    """0 = no cap."""
    name, _ = backend_key(provider)
    if name == "ollama" and settings.ollama_max_concurrency > 0:
        return settings.ollama_max_concurrency
    return max(settings.llm_max_concurrency, 0)


@contextlib.asynccontextmanager
async def model_slot(provider) -> AsyncIterator[None]:
    limit = backend_limit(provider)
    if limit <= 0:
        yield
        return
    global _loop
    loop = asyncio.get_running_loop()
    if loop is not _loop:
        _slots.clear()
        _loop = loop
    key = backend_key(provider)
    sem = _slots.get(key)
    if sem is None:
        sem = _slots[key] = asyncio.Semaphore(limit)
    async with sem:
        yield
