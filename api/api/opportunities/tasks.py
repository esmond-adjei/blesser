"""discover_opportunities: one agent task per audience category in a scan run."""

from sqlalchemy import or_, select

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
    PLANNER_SYSTEM_PROMPT,
)


def category_of(task) -> str:
    raw = (getattr(task, "target", None) or "").strip()
    category = raw.split(":", 1)[1] if raw.startswith("category:") else raw
    return category if category in CATEGORY_BRIEFS else "startup"


def user_message(
    *,
    region: str,
    category: str,
    focus: str,
    today: str,
    sites: list[str] | None = None,
    member: bool = False,
    sources_only: bool = False,
    repeat: bool = False,
    kinds: list[str] | None = None,
    planner: bool = False,
) -> str:
    focus = (focus or "").strip()
    sites = sites or []
    steps = ""
    if member:
        steps = (
            "This scan is for one member. Work in this order:\n"
            + (
                "1. Read the member's sites below with fetch_page, follow links on "
                "them to opportunity pages, and save what fits.\n"
                if sites
                else ""
            )
            + (
                "Only read the member's sites and pages they link to: this "
                "scheduled check does not search the web.\n\n"
                if sources_only
                else f"{2 if sites else 1}. Search the web for listings that fit the "
                "request and are new to the catalogue.\n\n"
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
        + (
            f"\nBudget: queue at most {settings.planner_max_picks} pages, then stop "
            "and summarize what you queued."
            if planner
            else f"\nBudget: save at most {settings.max_opportunities_per_task} "
            "opportunities in this task. Save each one as soon as it is verified, then "
            "stop and summarize what you saved and what you skipped."
        )
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
    if result is None and "seeded" not in (task.metrics or {}):
        from api.opportunities.pipeline import claimable, seed_region

        region = (scan.region or "").strip() or settings.opportunity_default_region
        seeded = (
            await seed_region(session, category, region)
            if scan.kind != "sources"
            and await claimable(session, category, region)
            < settings.seed_when_pool_below
            else []
        )
        task.metrics = {**(task.metrics or {}), "seeded": seeded}
        await session.commit()
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
            seeded=(task.metrics or {}).get("seeded") or [],
        )
        task.metrics = {
            **(task.metrics or {}),
            "agent_result": result,
            "agent_read": result.pop("read_pages", []),
            "agent_picked": result.pop("picked", []),
            "agent_seen": result.pop("seen", []),
        }
        task.messages_json = None
        await session.commit()
    handover = ("agent_read", "agent_picked", "seeded", "agent_seen")
    if any((task.metrics or {}).get(k) for k in handover):
        from api.opportunities.pipeline import hand_off

        metrics = task.metrics or {}
        await run_pipeline(
            session,
            task,
            scan,
            category,
            on_event,
            urls=await hand_off(
                session,
                metrics.get("agent_read") or [],
                category,
                picked=metrics.get("agent_picked") or [],
                seeded=metrics.get("seeded") or [],
                seen=metrics.get("agent_seen") or [],
                region=(scan.region or "").strip()
                or settings.opportunity_default_region,
            ),
        )
        task.metrics = {
            **{k: v for k, v in (task.metrics or {}).items() if k not in handover},
            "seeded_count": len(metrics.get("seeded") or []),
            "picked_count": len(metrics.get("agent_picked") or []),
        }
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
    tried = (task.metrics or {}).get("tried") or {}
    lines = [f"- searched: {q}" for q in tried.get("searches", [])] + [
        f"- read: {u}" for u in tried.get("pages", [])
    ]
    return (
        f"{focus}\n\nThe member has steered this run. Their note comes first and "
        f"overrides the notes above where they differ:\n{steer}"
        + (
            "\n\nEarlier runs of this scan already tried these. Don't repeat them: "
            "use new search terms, other organisations and other sites.\n"
            + "\n".join(lines)
            if lines
            else ""
        )
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
    seeded: list[str] = (),
) -> dict:
    from api.opportunities.tools import _scan_created, url_key

    region = (scan.region or "").strip() or settings.opportunity_default_region
    sites = list(scan.sites or []) if member else []
    sources_only = scan.kind == "sources"
    planner = settings.scan_agent_mode == "planner"
    message = user_message(
        region=region,
        category=category,
        focus=_focus(scan, task),
        today=opp_service.today().isoformat(),
        sites=sites,
        member=member,
        sources_only=sources_only,
        repeat=bool(scan.schedule_id) and scan.kind != "member",
        kinds=list(scan.kinds or []),
        planner=planner,
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
    for url in seeded:
        ctx.known_pages.setdefault(url, f"{url} | queued")
    if planner:
        tools = (["fetch_page"] if sites else []) + ["queue_pages"]
    else:
        tools = ["fetch_page", "save_opportunity", "reject_candidate"]
    if not sources_only:
        tools.insert(0, "search_web")
    result = await run_agent_task(
        PLANNER_SYSTEM_PROMPT if planner else DISCOVER_OPPORTUNITIES_SYSTEM_PROMPT,
        message,
        ctx,
        on_event=on_event,
        resume_messages=resume_messages,
        on_checkpoint=on_checkpoint,
        tools=tools,
        max_turns=settings.planner_max_turns
        if planner
        else settings.discovery_max_turns,
        no_yield_turns=settings.discovery_no_yield_turns,
    )
    await session.commit()
    return {
        "final_text": result["final_text"],
        "turns": result.get("turns"),
        "read_pages": ctx.read_pages,
        "picked": ctx.picked,
        "seen": ctx.seen_results,
    }


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
        f"Re-verify only {row.title} by {row.organization}. Read {row.source_url or row.link}. Save only this opportunity if the source still confirms it.{cycle}"
        " If neither the official page nor the application page it links to can be read,"
        " stop and say so: not saving is a valid answer, and search engines, proxies and"
        f" archives are not sources. Today: {opp_service.today().isoformat()}.",
        ctx,
        on_event=on_event,
        resume_messages=resume_messages,
        on_checkpoint=on_checkpoint,
        tools=["fetch_page", "save_opportunity"],
        max_turns=settings.reverify_max_turns,
    )
    await record_agent_check(session, task, started)
    await session.commit()
    return result
