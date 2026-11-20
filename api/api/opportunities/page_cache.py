import asyncio
from datetime import timedelta

import httpx
from lxml import etree
from sqlalchemy import func, select

from api.core import egress
from api.core.db import SessionLocal
from api.core.ids import new_id
from api.core.time import utcnow_naive
from api.editorial.service import get_settings
from api.opportunities.crawl_http import fetch_error, get_document
from api.opportunities.crawl_models import PageCache
from api.opportunities.page_content import Page, normalized_url, parse_page

_FETCHING = "fetch_in_progress"


def from_row(row: PageCache, cached: bool) -> Page:
    return Page(
        row.url,
        row.text,
        row.title,
        row.metadata_json,
        row.content_hash,
        row.error,
        cached,
    )


async def lock_url(session, key):
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext("page:" + key)))
    )


async def get_page(url: str) -> Page:
    key = normalized_url(url)
    delay = 0.05
    while True:
        token = None
        async with SessionLocal() as session:
            await lock_url(session, key)
            row = await session.get(PageCache, key)
            now = utcnow_naive()
            if row is not None and row.expires_at > now:
                if row.error != _FETCHING:
                    return from_row(row, True)
            else:
                config = (await get_settings(session))["crawler"]
                headers = {}
                if row is None:
                    row = PageCache(url=key, metadata_json={})
                    session.add(row)
                else:
                    if row.etag:
                        headers["If-None-Match"] = row.etag
                    if row.last_modified:
                        headers["If-Modified-Since"] = row.last_modified
                token = new_id()
                row.error = _FETCHING
                row.metadata_json = {**row.metadata_json, "_fetch_token": token}
                row.expires_at = now + timedelta(minutes=10)
                await session.commit()
        if token is None:
            await asyncio.sleep(delay)
            delay = min(1, delay * 2)
            continue
        response = None
        try:
            response, raw = await asyncio.wait_for(
                get_document(
                    url, interval=config["host_interval_seconds"], headers=headers
                ),
                timeout=300,
            )
            page = (
                None
                if response.status_code == 304
                else await asyncio.to_thread(parse_page, raw, key)
            )
            final = str(getattr(response, "url", "") or "")
            if page is not None and final and normalized_url(final) != key:
                # Redirected: scheduled checks treat a move to a homepage as a lost page.
                page.metadata["final_url"] = final
        except (
            httpx.HTTPError,
            egress.EgressBlocked,
            ValueError,
            TimeoutError,
            etree.ParserError,
            etree.XMLSyntaxError,
        ) as exc:
            page = Page(url=key, error=fetch_error(exc))
        async with SessionLocal() as session:
            await lock_url(session, key)
            row = await session.get(PageCache, key)
            if row is None or row.metadata_json.get("_fetch_token") != token:
                continue
            now = utcnow_naive()
            if page is None:
                row.error = ""
                row.metadata_json = {
                    k: v for k, v in row.metadata_json.items() if k != "_fetch_token"
                }
                ttl = config["page_cache_seconds"]
            else:
                row.text, row.title, row.metadata_json = (
                    page.text,
                    page.title,
                    page.metadata,
                )
                row.content_hash, row.error = page.content_hash, page.error
                row.etag = (
                    response.headers.get("etag", "")
                    if response is not None and not page.error
                    else ""
                )
                row.last_modified = (
                    response.headers.get("last-modified", "")
                    if response is not None and not page.error
                    else ""
                )
                ttl = (
                    min(config["page_cache_seconds"], 1800)
                    if page.error
                    else config["page_cache_seconds"]
                )
            row.fetched_at = now
            row.expires_at = now + timedelta(seconds=ttl)
            await session.commit()
            return from_row(row, page is None)
