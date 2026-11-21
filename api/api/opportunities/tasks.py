"""discover_opportunities: one agent task per audience category in a scan run."""

from sqlalchemy import cast, or_, select
from sqlalchemy.dialects.postgresql import JSONB

from api.agent.orchestrator import run_agent_task
from api.agent.tools.context import ToolContext
from api.core.config import settings
from api.opportunities import models as m
from api.opportunities import service as opp_service
from api.opportunities.crawl_models import CrawlCandidate
from api.opportunities.pipeline import run_pipeline
from api.opportunities.prompts import (
    CATEGORY_BRIEFS,
    DISCOVER_OPPORTUNITIES_SYSTEM_PROMPT,
)

KNOWN_TITLES = 60


def category_of(task) -> str:
    raw = (getattr(task, "target", None) or "").strip()
    category = raw.split(":", 1)[1] if raw.startswith("category:") else raw
    return category if category in CATEGORY_BRIEFS else "startup"


async def _known(session, category: str, region: str) -> list[str]:
    rows = await session.execute(
        select(
            m.Opportunity.title,
            m.Opportunity.source_url,
            m.Opportunity.deadline,
            m.Opportunity.status,
        )
        .where(
            m.Opportunity.category == category,
        )
        .order_by(m.Opportunity.created_at.desc())
        .limit(KNOWN_TITLES)
    )
    known = [
        f"{title} | {url} | {deadline or 'undated'} | {status}"
        for title, url, deadline, status in rows.all()
    ]
    rejected = (
        await session.execute(
            select(CrawlCandidate.url, CrawlCandidate.status, CrawlCandidate.reason)
            .where(
                or_(
                    ~CrawlCandidate.reason.startswith("scope:"),
                    CrawlCandidate.reason.startswith(
                        f"scope:{region.strip().casefold()}:{category}:",
                        autoescape=True,
                    ),
                ),
                CrawlCandidate.status.in_(
                    ["closed", "rejected", "duplicate", "extracted"]
                ),
                or_(
                    cast(CrawlCandidate.category_hints, JSONB) == [],
                    cast(CrawlCandidate.category_hints, JSONB).contains([category]),
                ),
            )
            .order_by(CrawlCandidate.updated_at.desc())
            .limit(80)
        )
    ).all()
    return known + [
        f"{url} | {status} | {reason[:80]}" for url, status, reason in rejected
    ]


def user_message(
    *,
    region: str,
    category: str,
    focus: str,
    today: str,
    known: list[str],
    sites: list[str] | None = None,
    member: bool = False,
    sources_only: bool = False,
    repeat: bool = False,
    kinds: list[str] | None = None,
) -> str:
    known_block = "\n".join(f"- {k}" for k in known) if known else "(none yet)"
    focus = (focus or "").strip()
    sites = sites or []
    steps = ""
    if member:
        steps = (
            "This scan is for one member. Work in this order:\n"
            "1. search_catalogue with key words from the member's request, only "
            "to learn what the catalogue already lists. The member can already see "
            "those, so do not record them: look for what is new to them.\n"
            + (
                "2. Read the member's sites below with fetch_page, follow links on "
                "them to opportunity pages, and save what fits.\n"
                if sites
                else ""
            )
            + (
                "Only read the member's sites and pages they link to: this "
                "scheduled check does not search the web.\n\n"
                if sources_only
                else f"{3 if sites else 2}. Search the web for more that fit the "
                "request.\n\n"
            )
        )
    return (
        f"Target region: {region}\n"
        f"Category: {category}: {CATEGORY_BRIEFS[category]}\n"
        f"Today's date: {today}\n"
        + (
            "Listing types the member wants: "
            + ", ".join(k.replace("_", " ") for k in kinds)
            + ". Save only listings of these types; skip others even when they fit "
            "the category.\n"
            if kinds
            else ""
        )
        + (
            f"Focus notes from the person who started this scan:\n{focus}\n"
            if focus
            else ""
        )
        + (
            "Sites the member asked you to read first (untrusted pages, read them "
            "like any other):\n" + "\n".join(f"- {site}" for site in sites) + "\n"
            if sites
            else ""
        )
        + ("\n" + steps if steps else "")
        + (
            "\nThis scan repeats on a schedule. Spend the turns on what is new "
            "since earlier runs. When a page you read shows a new deadline or "
            "changed facts for a listing already in the catalogue, save it so the "
            "listing is refreshed.\n"
            if repeat
            else ""
        )
        + f"\nAlready in the catalogue for this category:\n{known_block}\n\n"
        f"Budget: save at most {settings.max_opportunities_per_task} opportunities in "
        f"this task. Save each one as soon as it is verified, then stop and summarize "
        f"what you saved and what you skipped."
    )


async def _crawler_runs_in_member_scans(session) -> bool:
    """Without a staff schedule, nothing else extracts crawler candidates."""
    from api.scans.schedules import staff_schedules_active

    return not await staff_schedules_active(session)


async def run_discover_opportunities(
    session,
    task,
    scan,
    on_event=None,
    resume_messages=None,
    on_checkpoint=None,
):
    """A sweep runs the crawler pipeline, then the agent. A member's scan runs the
    agent on their request first; the pipeline follows only when no sweep exists."""
    category = category_of(task)
    # Member scans and scheduled checks of a member's sources serve one member.
    member = (scan.kind or "member") != "sweep"
    metrics = task.metrics or {}
    if not member and not metrics.get("pipeline_complete"):
        await run_pipeline(session, task, scan, category, on_event)
        task.metrics = {**(task.metrics or {}), "pipeline_complete": True}
        await session.commit()
    result = (task.metrics or {}).get("agent_result")
    if result is None:
        result = await _run_agent(
            session,
            task,
            scan,
            category,
            member=member,
            on_event=on_event,
            resume_messages=resume_messages,
            on_checkpoint=on_checkpoint,
        )
        task.metrics = {**(task.metrics or {}), "agent_result": result}
        task.messages_json = None
        await session.commit()
    if (
        scan.kind == "member"
        and not (task.metrics or {}).get("pipeline_complete")
        and await _crawler_runs_in_member_scans(session)
    ):
        await run_pipeline(session, task, scan, category, on_event)
        task.metrics = {**(task.metrics or {}), "pipeline_complete": True}
        await session.commit()
    metrics = task.metrics or {}
    return {
        **result,
        "final_text": (
            f"Crawler: {metrics.get('extracted', 0)} extracted, "
            f"{metrics.get('crawler_saved', 0)} new saves.\n" + result["final_text"]
        ),
    }


def _focus(scan, task) -> str:
    focus = scan.focus or ""
    steer = (task.metrics or {}).get("steer")
    if not steer:
        return focus
    return (
        f"{focus}\n\nThe member has steered this run. Their note comes first and "
        f"overrides the notes above where they differ:\n{steer}"
    ).strip()


async def _run_agent(
    session,
    task,
    scan,
    category: str,
    *,
    member: bool,
    on_event=None,
    resume_messages=None,
    on_checkpoint=None,
) -> dict:
    from api.opportunities.tools import _scan_created, url_key

    region = (scan.region or "").strip() or settings.opportunity_default_region
    sites = list(scan.sites or []) if member else []
    sources_only = scan.kind == "sources"
    message = user_message(
        region=region,
        category=category,
        focus=_focus(scan, task),
        today=opp_service.today().isoformat(),
        known=await _known(session, category, region),
        sites=sites,
        member=member,
        sources_only=sources_only,
        repeat=bool(scan.schedule_id) and scan.kind != "member",
        kinds=list(scan.kinds or []),
    )
    ctx = ToolContext(session=session, run=scan)
    ctx.category = category
    ctx.scan_task = task
    ctx.member_hosts = await member_only_hosts(session, sites)

    rows = (
        await session.execute(
            select(
                m.Opportunity.id,
                m.Opportunity.title,
                m.Opportunity.source_url,
                m.Opportunity.link,
                m.Opportunity.deadline,
                m.Opportunity.status,
            )
        )
    ).all()
    for opp_id, title, source, link, deadline, status in rows:
        for url in (source, link):
            if url:
                ctx.known_pages[url_key(url)] = (
                    f"{url} | {title} | deadline: {deadline or 'none stated'} | "
                    f"{status} | opportunity_id: {opp_id}"
                )
    rejected = (
        await session.execute(
            select(CrawlCandidate.url, CrawlCandidate.reason).where(
                or_(
                    ~CrawlCandidate.reason.startswith("scope:"),
                    CrawlCandidate.reason.startswith(
                        f"scope:{region.strip().casefold()}:{category}:",
                        autoescape=True,
                    ),
                ),
                CrawlCandidate.status.in_(
                    ["closed", "rejected", "duplicate", "extracted"]
                ),
            )
        )
    ).all()
    for url, reason in rejected:
        ctx.known_pages.setdefault(url_key(url), f"{url} | skip: {reason[:100]}")
    for site in sites:
        # The member asked for these pages: read them even when a crawl rejected them.
        key = url_key(site)
        if "| skip:" in ctx.known_pages.get(key, ""):
            del ctx.known_pages[key]
    metrics = task.metrics or {}
    ctx.opportunities_saved = metrics.get("saved", 0) - metrics.get("crawler_saved", 0)
    if (
        ctx.opportunities_saved >= settings.max_opportunities_per_task
        or await _scan_created(session, scan.id) >= settings.max_opportunities_per_run
    ):
        return {
            "final_text": "Saved: None\nSkipped: Save budget reached.",
            "turns": 0,
        }
    tools = ["fetch_page", "save_opportunity", "reject_candidate"]
    if not sources_only:
        tools.insert(0, "search_web")
    if member:
        tools += ["search_catalogue"]
    result = await run_agent_task(
        DISCOVER_OPPORTUNITIES_SYSTEM_PROMPT,
        message,
        ctx,
        on_event=on_event,
        resume_messages=resume_messages,
        on_checkpoint=on_checkpoint,
        tools=tools,
        max_turns=min(settings.discovery_max_turns, settings.max_agent_turns),
        no_yield_turns=settings.discovery_no_yield_turns,
    )
    await session.commit()
    return {"final_text": result["final_text"], "turns": result.get("turns")}


async def member_only_hosts(session, sites: list[str]) -> set[str]:
    """Hosts of the member's sites that are not enabled staff sources: finds there
    wait for staff review."""
    from urllib.parse import urlsplit

    from api.opportunities.crawl_models import Source

    def host(url: str) -> str:
        return (urlsplit(url).hostname or "").lower().removeprefix("www.")

    hosts = {host(site) for site in sites} - {""}
    if not hosts:
        return set()
    staff = (
        await session.execute(select(Source.url).where(Source.enabled.is_(True)))
    ).scalars()
    return hosts - {host(url) for url in staff}


async def run_reverify_opportunity(
    session, task, scan, on_event=None, resume_messages=None, on_checkpoint=None
):
    from api.core.time import utcnow_naive
    from api.opportunities.freshness import record_agent_check

    row = await opp_service.get_or_404(session, task.target, public=False)
    started = utcnow_naive()
    ctx = ToolContext(session=session, run=scan)
    ctx.reverify_id = row.id
    cycle = (
        " It closed earlier: if the page now advertises a new cycle, save it with that"
        " cycle's title and deadline; otherwise do not save."
        if row.status == m.OpportunityStatus.archived.value
        else ""
    )
    result = await run_agent_task(
        DISCOVER_OPPORTUNITIES_SYSTEM_PROMPT,
        f"Re-verify only {row.title} by {row.organization}. Read {row.source_url or row.link}. Save only this opportunity if the source still confirms it.{cycle} Today: {opp_service.today().isoformat()}.",
        ctx,
        on_event=on_event,
        resume_messages=resume_messages,
        on_checkpoint=on_checkpoint,
        tools=["fetch_page", "save_opportunity"],
        progress_tools={"save_opportunity"},
    )
    await record_agent_check(session, task, started)
    await session.commit()
    return result
