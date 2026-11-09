import asyncio
from datetime import timedelta
from urllib.parse import urlsplit

import httpx
from sqlalchemy import func, select

from api import web
from api.core import egress
from api.core.db import SessionLocal
from api.core.time import utcnow_naive
from api.opportunities.crawl_models import CrawlHost


async def reserve_host(url: str, interval: float) -> None:
    host = urlsplit(url).netloc.lower()
    async with SessionLocal() as session:
        await session.execute(
            select(func.pg_advisory_xact_lock(func.hashtext("crawl-host:" + host)))
        )
        row = await session.get(CrawlHost, host)
        now = utcnow_naive()
        if row is None:
            row = CrawlHost(host=host, next_request_at=now)
            session.add(row)
        when = max(row.next_request_at, now)
        row.next_request_at = when + timedelta(seconds=interval)
        await session.commit()
    await asyncio.sleep(max(0, (when - utcnow_naive()).total_seconds()))


async def get_document(url: str, *, interval: float, headers: dict | None = None):
    async def reserve(hop):
        await reserve_host(str(hop), interval)

    async def before(hop):
        if not await web._robots_allows(str(hop), before_request=reserve):
            raise egress.EgressBlocked("robots.txt disallows this page")
        await reserve(hop)

    response, text = await egress.safe_get(
        web.fetch_client(),
        url,
        max_bytes=web.settings.fetch_max_bytes,
        headers=headers,
        before_request=before,
    )
    if response.status_code != 304:
        response.raise_for_status()
    return response, text


def fetch_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_{exc.response.status_code}"
    if isinstance(exc, egress.EgressBlocked):
        return "blocked: " + str(exc)[:120]
    return type(exc).__name__
