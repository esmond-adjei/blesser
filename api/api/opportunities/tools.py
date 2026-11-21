"""Ground opportunity saves and remember rejected pages."""

from urllib.parse import urlsplit

from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from api.agent.tools.context import ToolContext
from api.applications.dates import parse_deadline
from api.core.config import settings
from api.opportunities import models as m
from api.opportunities import schemas
from api.opportunities import service as opp_service
from api.opportunities.page_content import dates_in, expired, normalized_url
from api.scans.models import ScanFind

#: Fetched text kept per page for grounding checks.
MAX_PAGE_CHARS = 400_000
_STOPWORDS = frozenset(
    [
        "the",
        "and",
        "for",
        "with",
        "from",
        "into",
        "of",
        "in",
        "on",
        "at",
        "to",
        "a",
        "an",
        "by",
        "or",
        "programme",
        "program",
        "call",
        "open",
        "2024",
        "2025",
        "2026",
        "2027",
        "2028",
    ]
)


def url_key(url: str) -> str:
    return normalized_url(url)


def record_fetch(ctx, url: str, text: str) -> None:
    """Called by fetch_page: remember what this task actually read."""
    pages = getattr(ctx, "fetched_pages", None)
    if pages is None:
        return
    key = url_key(url)
    if not (text or "").startswith("[Could not fetch"):
        pages[key] = (pages.get(key, "") + "\n" + (text or ""))[:MAX_PAGE_CHARS]


def _words(text: str) -> list[str]:
    return [
        w
        for w in opp_service.normalize(text).split()
        if len(w) >= 3 and w not in _STOPWORDS
    ]


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
    return deadline_date in dates_in(page)


def validate_grounding(
    data: schemas.AgentOpportunityIn, pages: dict[str, str]
) -> str | None:
    for url in (data.source_url, data.link or data.source_url):
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
        ):
            return "Source and application links must be public http(s) URLs."
    page = pages.get(url_key(data.source_url))
    if page is None:
        return "source_url must be a page you fetched with fetch_page in this task."
    if not names_opportunity(page, data.title, data.organization):
        return "The fetched source page doesn't name this opportunity."
    deadline = parse_deadline(data.deadline)
    if data.deadline.strip() and deadline is None:
        return "Use an unambiguous deadline date or leave it empty."
    if deadline is not None:
        if not deadline_on_page(page, deadline):
            return "That deadline isn't on the fetched page."
        if deadline < opp_service.today() and not data.rolling:
            return "This opportunity's deadline has passed: skip it."
    return None


async def _scan_created(session, scan_id: str, via: str | None = "agent") -> int:
    """Listings this scan added to the catalogue; by default only the agent's.

    Crawler saves have their own per-task limit, so they never use up the room the
    member's agent has.
    """
    query = (
        select(func.count())
        .select_from(ScanFind)
        .where(ScanFind.scan_id == scan_id, ScanFind.created.is_(True))
    )
    if via is not None:
        query = query.where(ScanFind.via == via)
    return (await session.execute(query)).scalar_one()


def member_site_host(ctx, url: str) -> str | None:
    """The member-supplied site host this URL is on, if any."""
    hosts = getattr(ctx, "member_hosts", None)
    if not hosts:
        return None
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return next(
        (h for h in hosts if host == h or host.endswith("." + h)),
        None,
    )


async def handle_save_opportunity(
    tool_input: dict, ctx: ToolContext, *, commit: bool = True
) -> dict:
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
    if ctx.reverify_id:
        target = await opp_service.get_or_404(
            ctx.session, ctx.reverify_id, public=False
        )
        from api.opportunities.dedupe import key_for

        if (
            await key_for(ctx.session, data.organization, data.title)
            != target.dedupe_key
        ):
            return {"error": "Only the requested opportunity may be re-verified."}
    pages = getattr(ctx, "fetched_pages", None) or {}
    if error := validate_grounding(data, pages):
        return {"error": error}
    scan_id = getattr(getattr(ctx, "run", None), "id", None)
    via = getattr(ctx, "save_via", "agent")
    if scan_id and via == "agent":
        await ctx.session.execute(
            select(func.pg_advisory_xact_lock(func.hashtext("scan-budget:" + scan_id)))
        )
    if (
        scan_id
        and via == "agent"
        and await _scan_created(ctx.session, scan_id)
        >= settings.max_opportunities_per_run
    ):
        return {
            "error": (
                f"Scan budget reached: {settings.max_opportunities_per_run} new opportunities "
                "per scan. Stop saving and write your final summary."
            )
        }
    member_host = member_site_host(ctx, data.source_url)
    opp, created, updated = await opp_service.upsert_from_agent(
        ctx.session,
        user_id=getattr(ctx, "user_id", None),
        scan_id=scan_id,
        data=data,
        low_confidence=getattr(ctx, "extraction_confidence", 1)
        < settings.extraction_min_confidence,
        review_note=(
            f"Found on {member_host}, a site a member asked a scan to check."
            if member_host
            else ""
        ),
    )
    if scan_id:
        find = insert(ScanFind).values(
            scan_id=scan_id,
            opportunity_id=opp.id,
            source_url=data.source_url if created else None,
            via=via,
            created=created,
            updated=bool(updated),
        )
        await ctx.session.execute(
            find.on_conflict_do_update(
                index_elements=[ScanFind.scan_id, ScanFind.opportunity_id],
                set_={"updated": ScanFind.updated | find.excluded.updated},
            )
            if updated
            else find.on_conflict_do_nothing()
        )
    from api.opportunities.crawler import propose_source, record_candidate

    source_id = await propose_source(ctx.session, data.source_url, data.category.value)
    added = await record_candidate(
        ctx.session,
        data.source_url,
        source_id=source_id,
        category_hints=[data.category.value],
        title=data.title,
        status="extracted",
        reason="agent_save",
    )
    if getattr(ctx, "scan_task", None) is not None and created:
        from api.opportunities.crawl_models import Source

        await ctx.session.execute(
            update(Source)
            .where(Source.id == source_id)
            .values(
                opportunities_saved=Source.opportunities_saved + 1,
                candidates_found=Source.candidates_found + int(added),
            )
        )
    if created and getattr(ctx, "scan_task", None) is not None:
        ctx.scan_task.metrics = {
            **(ctx.scan_task.metrics or {}),
            "saved": (ctx.scan_task.metrics or {}).get("saved", 0) + 1,
        }
    if commit:
        await ctx.session.commit()
    notes = getattr(ctx, "page_notes", {})
    key = url_key(data.source_url)
    if key in notes:
        notes[key] = notes[key].rsplit(" | ", 1)[0] + " | saved: " + data.title
    ctx.opportunities_saved = saved + 1
    if created:
        ctx.saved_titles.append(opp.title)
    return {
        "opportunity_id": opp.id,
        "created": created,
        "updated_fields": updated,
        "deadline_date": opp.deadline_date.isoformat() if opp.deadline_date else None,
        "status": opp.status,
    }


async def handle_reject_candidate(tool_input: dict, ctx: ToolContext) -> dict:
    url = tool_input.get("url", "")
    if url_key(url) not in ctx.fetched_pages:
        return {"error": "Fetch the page before rejecting it."}
    reason = str(tool_input.get("reason", "irrelevant"))[:500]
    closed = bool(tool_input.get("closed")) and expired(
        ctx.fetched_pages[url_key(url)], {}, opp_service.today()
    )
    status = "closed" if closed else "rejected"
    if not closed:
        region = (getattr(ctx.run, "region", "") or "").strip().casefold()
        reason = f"scope:{region}:{ctx.category}:" + reason
    from api.opportunities.crawl_models import CrawlCandidate
    from api.opportunities.crawler import record_candidate

    await record_candidate(
        ctx.session,
        url,
        category_hints=[ctx.category] if closed else [],
        status=status,
        reason=reason,
    )
    row = (
        await ctx.session.execute(
            select(CrawlCandidate)
            .where(CrawlCandidate.url == url_key(url))
            .with_for_update()
        )
    ).scalar_one()
    if row.claim_token:
        return {"error": "This candidate is already being processed."}
    if row.status == "new" or row.reason.startswith("scope:"):
        row.status, row.reason = status, reason
        if not closed:
            row.category_hints = []
    await ctx.session.commit()
    return {"url": url, "verdict": status, "reason": reason}


#: Catalogue listings one task may match to the member's request.
MAX_CATALOGUE_MATCHES = 15


async def handle_search_catalogue(tool_input: dict, ctx: ToolContext) -> dict:
    """Open, published listings in this task's category matching the words."""
    from api.opportunities.service import list_public

    query = str(tool_input.get("query", ""))[:200]
    page = await list_public(
        ctx.session,
        q=query,
        category=ctx.category,
        sort="deadline",
        limit=10,
    )
    if not page["items"] and len(query.split()) > 1:
        # Every word must match; retry on each word alone, best first.
        seen: dict[str, dict] = {}
        for word in query.split()[:4]:
            more = await list_public(
                ctx.session, q=word, category=ctx.category, limit=5
            )
            for item in more["items"]:
                seen.setdefault(item["id"], item)
        page = {"items": list(seen.values())[:10]}
    return {
        "results": [
            {
                "opportunity_id": item["id"],
                "title": item["title"],
                "organization": item["organization"],
                "kind": item["kind"],
                "deadline": item["deadline_date"]
                or ("rolling" if item["rolling"] else ""),
                "location": item["location"],
                "summary": (item["summary"] or "")[:240],
                "eligibility": (item["eligibility"] or "")[:240],
            }
            for item in page["items"]
        ]
    }


async def handle_add_catalogue_match(tool_input: dict, ctx: ToolContext) -> dict:
    """Record an existing listing as a result of this member's scan."""
    scan_id = getattr(getattr(ctx, "run", None), "id", None)
    if not scan_id:
        return {"error": "Matches belong to a scan."}
    matched = getattr(ctx, "catalogue_matches", set())
    if len(matched) >= MAX_CATALOGUE_MATCHES:
        return {
            "error": f"Match limit reached ({MAX_CATALOGUE_MATCHES}). Keep only the best fits."
        }
    opp_id = str(tool_input.get("opportunity_id", ""))
    opp = await ctx.session.get(m.Opportunity, opp_id)
    if (
        opp is None
        or opp.status != m.OpportunityStatus.published.value
        or not opp_service.is_open(opp)
    ):
        return {"error": "Only open, published listings can be matched."}
    result = await ctx.session.execute(
        insert(ScanFind)
        .values(
            scan_id=scan_id,
            opportunity_id=opp.id,
            source_url=None,
            via="catalog",
            created=False,
        )
        .on_conflict_do_nothing()
        .returning(ScanFind.opportunity_id)
    )
    added = result.scalar_one_or_none() is not None
    await ctx.session.commit()
    matched.add(opp.id)
    ctx.catalogue_matches = matched
    return {"opportunity_id": opp.id, "title": opp.title, "added": added}
