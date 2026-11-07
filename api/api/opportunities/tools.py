"""save_opportunity: the discovery agent's only write, grounded in a fetched page.

A save must cite a page fetch_page returned in the same task (source_url), the
page must name the opportunity, and a stated deadline must appear on it. That
keeps the public catalogue to what a real page says, not what a model recalls.
"""

import re
from urllib.parse import urlsplit, urlunsplit

from pydantic import ValidationError
from sqlalchemy import func, select

from api.agent.tools.context import ToolContext
from api.applications.dates import parse_deadline
from api.core.config import settings
from api.opportunities import models as m
from api.opportunities import schemas
from api.opportunities import service as opp_service

#: Fetched text kept per page for grounding checks.
MAX_PAGE_CHARS = 400_000
_STOPWORDS = frozenset(
    ["the", "and", "for", "with", "from", "into", "of", "in", "on", "at", "to", "a", "an", "by", "or", "programme", "program", "call", "open", "2024", "2025", "2026", "2027", "2028"]
)
_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]


def url_key(url: str) -> str:
    """Scheme, host case, fragment and a trailing slash don't make a different page."""
    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        return (url or "").strip()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", parts.netloc.lower().removeprefix("www."), path, parts.query, ""))


def record_fetch(ctx, url: str, text: str) -> None:
    """Called by fetch_page: remember what this task actually read."""
    pages = getattr(ctx, "fetched_pages", None)
    if pages is None:
        return
    key = url_key(url)
    pages[key] = (pages.get(key, "") + "\n" + (text or ""))[:MAX_PAGE_CHARS]


def _words(text: str) -> list[str]:
    return [w for w in opp_service.normalize(text).split() if len(w) >= 3 and w not in _STOPWORDS]


def names_opportunity(page: str, title: str, organization: str) -> bool:
    """Most of the title's distinctive words, or the organization's, are on the page."""
    haystack = f" {opp_service.normalize(page)} "
    title_words = _words(title)
    if title_words:
        found = sum(1 for w in title_words if f" {w} " in haystack)
        if found / len(title_words) >= 0.6:
            return True
    org = opp_service.normalize(organization)
    return bool(org) and f" {org} " in haystack


def deadline_on_page(page: str, deadline_date) -> bool:
    """The year, and the month or day, of a stated deadline appear on the page."""
    text = page.lower()
    if str(deadline_date.year) not in text:
        return False
    month = _MONTHS[deadline_date.month - 1]
    if month in text or month[:3] in re.findall(r"[a-z]+", text):
        return True
    return bool(re.search(rf"(?<!\d)0?{deadline_date.day}(?!\d)", text))


async def _scan_created(session, scan_id: str) -> int:
    return (
        await session.execute(
            select(func.count()).select_from(m.Opportunity).where(m.Opportunity.scan_id == scan_id)
        )
    ).scalar_one()


async def handle_save_opportunity(tool_input: dict, ctx: ToolContext) -> dict:
    saved = getattr(ctx, "opportunities_saved", 0)
    if saved >= settings.max_opportunities_per_task:
        return {
            "error": (
                f"Budget reached: {settings.max_opportunities_per_task} opportunities per task. "
                "Stop saving and write your final summary."
            )
        }
    try:
        data = schemas.AgentOpportunityIn(**tool_input)
    except ValidationError as exc:
        return {"error": f"Invalid opportunity: {exc.errors()[0].get('msg', exc)}"}
    pages = getattr(ctx, "fetched_pages", None) or {}
    page = pages.get(url_key(data.source_url))
    if page is None:
        return {
            "error": (
                "source_url must be a page you fetched with fetch_page in this task. "
                "Fetch the opportunity's page first, then save it with that URL."
            )
        }
    if not names_opportunity(page, data.title, data.organization):
        return {
            "error": (
                "The fetched source page doesn't name this opportunity: use the title "
                "and organization as the page writes them, or fetch the right page."
            )
        }
    deadline_date = parse_deadline(data.deadline)
    if data.deadline.strip() and deadline_date is not None:
        if not deadline_on_page(page, deadline_date):
            return {
                "error": (
                    "That deadline isn't on the fetched page. Copy the deadline as the "
                    "page states it, or leave it empty when the page gives none."
                )
            }
        if deadline_date < opp_service.today() and not data.rolling:
            return {"error": "This opportunity's deadline has passed: skip it."}
    scan_id = getattr(getattr(ctx, "run", None), "id", None)
    if scan_id and await _scan_created(ctx.session, scan_id) >= settings.max_opportunities_per_run:
        return {
            "error": (
                f"Scan budget reached: {settings.max_opportunities_per_run} new opportunities "
                "per scan. Stop saving and write your final summary."
            )
        }
    opp, created, updated = await opp_service.upsert_from_agent(
        ctx.session, user_id=getattr(ctx, "user_id", None), scan_id=scan_id, data=data
    )
    await ctx.session.commit()
    ctx.opportunities_saved = saved + 1
    return {
        "opportunity_id": opp.id,
        "created": created,
        "updated_fields": updated,
        "deadline_date": opp.deadline_date.isoformat() if opp.deadline_date else None,
        "status": opp.status,
    }
