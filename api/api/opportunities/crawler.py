import asyncio
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit

import httpx
from lxml import etree
from lxml import html as lxml_html
from sqlalchemy import cast, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB, insert

from api.core import egress
from api.core.ids import new_id
from api.core.time import utcnow_naive
from api.editorial.service import get_settings
from api.opportunities.crawl_http import fetch_error, get_document
from api.opportunities.crawl_models import CrawlCandidate, Source
from api.opportunities.page_content import normalized_url
from api.opportunities.triage import is_social_host

_LEAD_WORDS = (
    "grant",
    "funding",
    "award",
    "scholarship",
    "fellowship",
    "accelerator",
    "incubat",
    "internship",
    "competition",
    "call for",
    "apply",
    "programme",
    "program",
    "opportunit",
)


def published_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        try:
            return parsedate_to_datetime(raw).date()
        except (ValueError, TypeError):
            return None


def newest_first(nodes) -> list[tuple[str, date | None]]:
    """(loc, lastmod) of sitemap entries, most recently changed first, undated last."""
    entries = []
    for index, node in enumerate(nodes):
        loc = node.xpath('./*[local-name()="loc"]/text()')
        if not loc or not loc[0].strip():
            continue
        lastmod = node.xpath('./*[local-name()="lastmod"]/text()')
        modified = published_date(lastmod[0].strip()) if lastmod else None
        entries.append((loc[0].strip(), modified, index))
    entries.sort(key=lambda e: (e[1] is None, -(e[1].toordinal() if e[1] else 0), e[2]))
    return [(loc, modified) for loc, modified, _ in entries]


def parse_items(
    raw: str, url: str, kind: str, limit: int
) -> tuple[list[dict], list[str]]:
    items, maps = [], []
    if kind in {"rss", "sitemap"}:
        tree = etree.fromstring(
            raw.encode(),
            parser=etree.XMLParser(
                resolve_entities=False, no_network=True, recover=True
            ),
        )
        if tree is None:
            raise ValueError("empty XML")
        root = etree.QName(tree).localname.lower()
        if root not in (
            {"urlset", "sitemapindex"} if kind == "sitemap" else {"rss", "feed", "rdf"}
        ):
            raise ValueError("not a feed or sitemap")
        if kind == "sitemap":
            maps = [
                loc
                for loc, _ in newest_first(tree.xpath('//*[local-name()="sitemap"]'))
            ][:5]
            for loc, modified in newest_first(tree.xpath('//*[local-name()="url"]'))[
                :limit
            ]:
                items.append({"url": loc, "title": "", "published_date": modified})
        else:
            for node in tree.xpath('//*[local-name()="item" or local-name()="entry"]')[
                :limit
            ]:
                links = node.xpath('./*[local-name()="link"]/text()') or node.xpath(
                    './*[local-name()="link"][@rel="alternate" or not(@rel)]/@href'
                )
                title = node.xpath('./*[local-name()="title"]/text()')
                pub = node.xpath(
                    './*[local-name()="pubDate" or local-name()="published"]/text()'
                )
                if links:
                    items.append(
                        {
                            "url": urljoin(url, links[0]),
                            "title": (title[0] if title else "")[:300],
                            "published_date": published_date(pub[0]) if pub else None,
                        }
                    )
    else:
        tree = lxml_html.fromstring(raw)
        for node in tree.xpath("//nav|//footer|//body/header|//script|//style"):
            node.drop_tree()
        for node in tree.xpath("//a[@href]"):
            label = " ".join(node.text_content().split())
            href = urljoin(url, node.get("href", ""))
            words = (label + " " + href).lower().replace("-", " ").replace("_", " ")
            if not any(word in words for word in _LEAD_WORDS):
                continue
            if is_social_host(href):
                continue
            if label.lower().startswith(
                ("about ", "faq", "our past", "grants awarded")
            ) or urlsplit(href).path.rstrip("/").endswith(
                ("/register", "/login", "/sign-in")
            ):
                continue
            if normalized_url(href) == normalized_url(url):
                continue
            items.append({"url": href, "title": label[:300], "published_date": None})
    unique = {}
    for item in items:
        p = urlsplit(item["url"])
        if (
            p.scheme not in {"http", "https"}
            or p.username
            or not p.netloc
            or p.path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".zip"))
        ):
            continue
        item["url"] = normalized_url(item["url"])
        unique.setdefault(item["url"], item)
    return list(unique.values())[:limit], maps


async def record_candidate(
    session,
    url: str,
    *,
    category_hints=None,
    source_id=None,
    title="",
    published_date=None,
    status="new",
    reason="",
) -> bool:
    values = {
        "id": new_id(),
        "url": normalized_url(url),
        "source_id": source_id,
        "category_hints": category_hints or [],
        "title": title[:300],
        "published_date": published_date,
        "status": status,
        "reason": reason,
        "content_hash": "",
        "dedupe_key": "",
        "created_at": utcnow_naive(),
        "updated_at": utcnow_naive(),
    }
    result = await session.execute(
        insert(CrawlCandidate)
        .values(**values)
        .on_conflict_do_nothing(index_elements=[CrawlCandidate.url])
        .returning(CrawlCandidate.id)
    )
    return result.scalar_one_or_none() is not None


async def crawl_due(session, *, categories: list[str] | None = None) -> dict:
    config = (await get_settings(session))["crawler"]
    report = {"candidates_found": 0, "sources": {}}
    for _ in range(config["max_sources"]):
        query = (
            select(Source)
            .where(
                or_(Source.enabled.is_(True), on_trial()),
                or_(
                    Source.next_crawl_at <= utcnow_naive(),
                    Source.crawl_requested.is_(True),
                ),
            )
            .order_by(Source.next_crawl_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if config["hours"] <= 0:
            query = query.where(Source.crawl_requested.is_(True))
        if categories:
            query = query.where(
                or_(
                    cast(Source.category_hints, JSONB) == [],
                    *[
                        cast(Source.category_hints, JSONB).contains([c])
                        for c in categories
                    ],
                )
            )
        source = (await session.execute(query)).scalar_one_or_none()
        if source is None:
            await session.commit()
            break
        now = utcnow_naive()
        source.last_crawled_at = now
        source.next_crawl_at = now + timedelta(
            hours=max(1, config["hours"])
            * min(8, 2 ** min(source.consecutive_failures, 3))
        )
        source.crawl_requested = False
        headers = {}
        if source.etag:
            headers["If-None-Match"] = source.etag
        if source.last_modified:
            headers["If-Modified-Since"] = source.last_modified
        await session.commit()
        added = seen = 0
        error = ""
        try:
            response, raw = await get_document(
                source.url, interval=config["host_interval_seconds"], headers=headers
            )
            if response.status_code != 304:
                items, maps = await asyncio.to_thread(
                    parse_items,
                    raw,
                    source.url,
                    source.kind,
                    config["max_items_per_source"],
                )
                for child in maps:
                    if len(items) >= config["max_items_per_source"]:
                        break
                    child_url = urljoin(source.url, child)
                    if urlsplit(child_url).netloc != urlsplit(source.url).netloc:
                        continue
                    _, child_raw = await get_document(
                        child_url, interval=config["host_interval_seconds"]
                    )
                    children, _ = parse_items(
                        child_raw,
                        child_url,
                        "sitemap",
                        config["max_items_per_source"] - len(items),
                    )
                    items.extend(children)
                for item in items:
                    seen += 1
                    added += int(
                        await record_candidate(
                            session,
                            **item,
                            category_hints=source.category_hints,
                            source_id=source.id,
                        )
                    )
                source.etag = response.headers.get("etag", "")
                source.last_modified = response.headers.get("last-modified", "")
            source.consecutive_failures = 0
            source.last_error = ""
        except (
            httpx.HTTPError,
            egress.EgressBlocked,
            ValueError,
            etree.XMLSyntaxError,
            etree.ParserError,
        ) as exc:
            error = fetch_error(exc)
            source.consecutive_failures += 1
            source.last_error = error
        await session.execute(
            update(Source)
            .where(Source.id == source.id)
            .values(candidates_found=Source.candidates_found + added)
        )
        source.last_candidates = added
        await session.commit()
        report["sources"][source.url] = {"seen": seen, "new": added, "error": error}
        report["candidates_found"] += added
    return report


#: A suggested page is crawled on trial until it has yielded this many candidates.
TRIAL_CANDIDATES = 20
#: Links to opportunities a page needs before it is suggested as a source.
HUB_LINKS = 6


def on_trial():
    """Suggested pages that are not a site's homepage and are still within their trial."""
    return (
        Source.proposed.is_(True)
        & Source.enabled.is_(False)
        & Source.url.op("~")(r"^https?://[^/]+/.+")
        & (Source.candidates_found < TRIAL_CANDIDATES)
    )


async def source_for_host(session, url: str) -> str | None:
    """An existing source on this URL's site, preferring enabled ones."""
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    for source in (
        await session.execute(
            select(Source).order_by(Source.enabled.desc(), Source.created_at)
        )
    ).scalars():
        if (urlsplit(source.url).hostname or "").lower().removeprefix("www.") == host:
            return source.id
    return None


async def propose_source(
    session, url: str, category: str, *, feeds: list[str] | None = None
) -> str | None:
    """Suggest this page (or its own section feed) as a source on trial.

    A site already read in full by an enabled feed or sitemap gets no new source."""
    page = urlsplit(url)
    host = (page.hostname or "").lower().removeprefix("www.")
    path = page.path.rstrip("/")
    if not host or not path:
        return None
    for source in (await session.execute(select(Source))).scalars():
        if (urlsplit(source.url).hostname or "").lower().removeprefix("www.") != host:
            continue
        if normalized_url(source.url) == normalized_url(url) or (
            source.enabled and source.kind in ("rss", "sitemap")
        ):
            return source.id
    feed = next(
        (f for f in feeds or [] if urlsplit(f).path.startswith(path + "/")), None
    )
    target, kind = (feed, "rss") if feed else (url, "listing")
    await session.execute(
        insert(Source)
        .values(
            id=new_id(),
            url=target,
            kind=kind,
            category_hints=[category],
            enabled=False,
            proposed=True,
            next_crawl_at=utcnow_naive(),
            crawl_requested=False,
            etag="",
            last_modified="",
            consecutive_failures=0,
            last_error="",
            candidates_found=0,
            opportunities_saved=0,
            last_candidates=0,
            created_at=utcnow_naive(),
        )
        .on_conflict_do_nothing(index_elements=[Source.url])
    )
    return (
        await session.execute(select(Source.id).where(Source.url == target))
    ).scalar_one()


async def credit_source(session, source_id: str) -> None:
    """Count a new listing for a source; a suggested page on trial that yields one is
    switched on. Staff can still switch it off."""
    await session.execute(
        update(Source)
        .where(Source.id == source_id)
        .values(opportunities_saved=Source.opportunities_saved + 1)
    )
    await session.execute(
        update(Source)
        .where(Source.id == source_id, on_trial())
        .values(enabled=True, proposed=False)
    )
