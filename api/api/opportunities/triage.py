from datetime import date
from urllib.parse import urlsplit

from sqlalchemy import or_, select

from api.opportunities.crawl_models import CrawlCandidate
from api.opportunities.dedupe import dedupe_key, load_aliases
from api.opportunities.models import Opportunity
from api.opportunities.page_content import Page, expired, normalized_url

#: Social and video hosts: their pages are never an opportunity's source.
SOCIAL_HOSTS = frozenset(
    {
        "facebook.com",
        "twitter.com",
        "x.com",
        "linkedin.com",
        "instagram.com",
        "youtube.com",
    }
)


def is_social_host(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return any(host == social or host.endswith("." + social) for social in SOCIAL_HOSTS)


async def duplicate_url(session, url: str) -> bool:
    key = normalized_url(url)
    return (
        await session.execute(
            select(Opportunity.id)
            .where(
                or_(
                    Opportunity.source_url_key == key,
                    Opportunity.link_key == key,
                    Opportunity.found_via_url == key,
                )
            )
            .limit(1)
        )
    ).first() is not None


async def triage_page(
    session, candidate: CrawlCandidate, page: Page, today: date
) -> str | None:
    if page.error.startswith("pdf_"):
        # A PDF that is too large, locked, scanned or broken stays that way:
        # reject it instead of retrying it as a temporary fetch failure.
        return page.error
    if page.error:
        return "fetch_failed:" + page.error
    if len(page.text.strip()) < 120:
        return "empty_page"
    keys = []
    aliases = await load_aliases(session)

    def visit(value):
        if isinstance(value, dict):
            name = value.get("name")
            organization = next(
                (
                    value[key]
                    for key in ("funder", "provider", "hiringOrganization", "organizer")
                    if value.get(key)
                ),
                None,
            )
            if isinstance(organization, dict):
                organization = organization.get("name")
            if isinstance(name, str) and isinstance(organization, str):
                keys.append(dedupe_key(organization, name, aliases))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(page.metadata.get("structured", []))
    if (
        keys
        and (
            await session.execute(
                select(Opportunity.id)
                .where(
                    Opportunity.dedupe_key.in_(keys),
                    # A closed listing may be reopened by a new cycle on another page.
                    Opportunity.status != "archived",
                )
                .limit(1)
            )
        ).first()
    ):
        return "dedupe_key"
    if expired(page.text, page.metadata, today):
        return "deadline_passed"
    previous = (
        await session.execute(
            select(CrawlCandidate.id)
            .where(
                CrawlCandidate.id != candidate.id,
                CrawlCandidate.content_hash == page.content_hash,
                CrawlCandidate.status != "new",
                ~CrawlCandidate.reason.startswith("scope:"),
            )
            .limit(1)
        )
    ).first()
    return "content_duplicate" if previous else None


async def triage_url(session, candidate: CrawlCandidate) -> str | None:
    if await duplicate_url(session, candidate.url):
        return "url_duplicate"
    from api.opportunities.service import blocks_save

    if candidate.dedupe_key and await blocks_save(session, candidate.dedupe_key):
        return "dedupe_key"
    parsed = urlsplit(candidate.url)
    if is_social_host(candidate.url):
        return "navigation"
    path = parsed.path.lower().rstrip("/")
    if (
        path.endswith(
            (
                "/register",
                "/login",
                "/research-careers",
                "/what-we-do",
                "/tef-past-programmes",
            )
        )
        or "/faq" in path
    ):
        return "navigation"
    return None


def is_listing(page: Page) -> bool:
    path = urlsplit(page.url).path.rstrip("/")
    return bool(page.metadata.get("links")) and (
        page.title.lower().startswith(
            (
                "find funding",
                "master's degree",
                "master’s degree",
                "phd level",
                "postdocs",
                "scholarship database",
            )
        )
        or path.endswith("/programs")
    )
