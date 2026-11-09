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
    *, region: str, category: str, focus: str, today: str, known: list[str]
) -> str:
    known_block = "\n".join(f"- {k}" for k in known) if known else "(none yet)"
    focus = (focus or "").strip()
    return (
        f"Target region: {region}\n"
        f"Category: {category}: {CATEGORY_BRIEFS[category]}\n"
        f"Today's date: {today}\n"
        + (
            f"Focus notes from the person who started this scan:\n{focus}\n"
            if focus
            else ""
        )
        + f"\nAlready in the catalogue for this category:\n{known_block}\n\n"
        f"Budget: save at most {settings.max_opportunities_per_task} opportunities in "
        f"this task. Save each one as soon as it is verified, then stop and summarize "
        f"what you saved and what you skipped."
    )


async def run_discover_opportunities(
    session,
    task,
    scan,
    on_event=None,
    resume_messages=None,
    on_checkpoint=None,
):
    category = category_of(task)
    if not (task.metrics or {}).get("pipeline_complete"):
        await run_pipeline(session, task, scan, category, on_event)
        task.metrics = {**(task.metrics or {}), "pipeline_complete": True}
        await session.commit()
    region = (scan.region or "").strip() or settings.opportunity_default_region
    focus = scan.focus or ""
    message = user_message(
        region=region,
        category=category,
        focus=focus,
        today=opp_service.today().isoformat(),
        known=await _known(session, category, region),
    )
    ctx = ToolContext(session=session, run=scan)
    ctx.category = category
    ctx.scan_task = task
    from api.opportunities.tools import url_key

    rows = (
        await session.execute(
            select(
                m.Opportunity.title,
                m.Opportunity.source_url,
                m.Opportunity.link,
                m.Opportunity.deadline,
                m.Opportunity.status,
            )
        )
    ).all()
    for title, source, link, deadline, status in rows:
        for url in (source, link):
            if url:
                ctx.known_pages[url_key(url)] = (
                    f"{url} | {title} | deadline: {deadline or 'none stated'} | {status}"
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
    ctx.opportunities_saved = (task.metrics or {}).get("saved", 0)
    from api.opportunities.tools import _scan_created

    if (
        ctx.opportunities_saved >= settings.max_opportunities_per_task
        or await _scan_created(session, scan.id) >= settings.max_opportunities_per_run
    ):
        return {
            "final_text": f"Saved: {ctx.opportunities_saved} pipeline records.\nSkipped: Save budget reached.",
            "turns": 0,
        }
    result = await run_agent_task(
        DISCOVER_OPPORTUNITIES_SYSTEM_PROMPT,
        message,
        ctx,
        on_event=on_event,
        resume_messages=resume_messages,
        on_checkpoint=on_checkpoint,
        tools=["search_web", "fetch_page", "save_opportunity", "reject_candidate"],
        max_turns=min(settings.discovery_max_turns, settings.max_agent_turns),
        no_yield_turns=settings.discovery_no_yield_turns,
    )

    await session.commit()
    result["final_text"] = (
        f"Crawler: {(task.metrics or {}).get('extracted', 0)} extracted, {(task.metrics or {}).get('saved', 0)} new saves across pipeline and agent.\n"
        + result["final_text"]
    )
    return result


async def run_reverify_opportunity(
    session, task, scan, on_event=None, resume_messages=None, on_checkpoint=None
):
    row = await opp_service.get_or_404(session, task.target, public=False)
    ctx = ToolContext(session=session, run=scan)
    ctx.reverify_id = row.id
    return await run_agent_task(
        DISCOVER_OPPORTUNITIES_SYSTEM_PROMPT,
        f"Re-verify only {row.title} by {row.organization}. Read {row.source_url}. Save only this opportunity if the source still confirms it. Today: {opp_service.today().isoformat()}.",
        ctx,
        on_event=on_event,
        resume_messages=resume_messages,
        on_checkpoint=on_checkpoint,
        tools=["fetch_page", "save_opportunity"],
        progress_tools={"save_opportunity"},
    )
