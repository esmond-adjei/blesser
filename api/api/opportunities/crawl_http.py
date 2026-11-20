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
from api.opportunities.pdf_text import PdfBody, declared_pdf, has_pdf_magic


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


def _pdf_limit(response: httpx.Response) -> int:
    """Byte cap for one response: PDFs get their own, larger cap.

    A declared length over the cap reads one byte, so the file is refused
    without downloading it."""
    if not declared_pdf(
        response.headers.get("content-type", ""), response.request.url.path
    ):
        return web.settings.fetch_max_bytes
    cap = web.settings.pdf_max_bytes
    try:
        declared = int(response.headers.get("content-length") or 0)
    except ValueError:
        declared = 0
    return 0 if declared > cap else cap


async def get_document(
    url: str,
    *,
    interval: float,
    headers: dict | None = None,
    allow_pdf: bool = False,
):
    """(response, body). The body is text, or a `PdfBody` when `allow_pdf` is set
    and the response is a PDF by its headers, URL or leading bytes."""

    async def reserve(hop):
        await reserve_host(str(hop), interval)

    async def before(hop):
        if not await web._robots_allows(str(hop), before_request=reserve):
            raise egress.EgressBlocked("robots.txt disallows this page")
        await reserve(hop)

    if not allow_pdf:
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
    response, raw = await egress.safe_get(
        web.fetch_client(),
        url,
        max_bytes=web.settings.fetch_max_bytes,
        headers=headers,
        before_request=before,
        byte_limit=_pdf_limit,
        decode=False,
    )
    if response.status_code == 304:
        return response, ""
    response.raise_for_status()
    assert isinstance(raw, bytes)
    limit = _pdf_limit(response)
    content_type = response.headers.get("content-type", "")
    if declared_pdf(content_type, response.request.url.path) or (
        "html" not in content_type.lower() and has_pdf_magic(raw)
    ):
        return response, PdfBody(raw[:limit], truncated=len(raw) > limit)
    cap = web.settings.fetch_max_bytes
    return response, raw[:cap].decode(response.encoding or "utf-8", errors="replace")


def fetch_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_{exc.response.status_code}"
    if isinstance(exc, egress.EgressBlocked):
        return "blocked: " + str(exc)[:120]
    return type(exc).__name__
