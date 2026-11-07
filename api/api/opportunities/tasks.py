"""discover_opportunities: one agent task per audience category in a scan run."""

from sqlalchemy import select

from api.agent.orchestrator import run_agent_task
from api.agent.tools.context import ToolContext
from api.core.config import settings
from api.opportunities import models as m
from api.opportunities import service as opp_service
from api.opportunities.prompts import (
    CATEGORY_BRIEFS,
    DISCOVER_OPPORTUNITIES_SYSTEM_PROMPT,
)

TASK_TYPE = "discover_opportunities"
#: Titles of known opportunities shown to the agent so it looks for new ones.
KNOWN_TITLES = 60


def category_of(task) -> str:
    raw = (getattr(task, "target_name", None) or "").strip()
    category = raw.split(":", 1)[1] if raw.startswith("category:") else raw
    return category if category in CATEGORY_BRIEFS else "startup"


async def _known(session, category: str) -> list[str]:
    rows = await session.execute(
        select(m.Opportunity.title, m.Opportunity.organization)
        .where(
            m.Opportunity.category == category,
            m.Opportunity.status != m.OpportunityStatus.hidden.value,
        )
        .order_by(m.Opportunity.created_at.desc())
        .limit(KNOWN_TITLES)
    )
    return [f"{t} ({o})" if o else t for t, o in rows.all()]


def user_message(*, region: str, category: str, focus: str, today: str, known: list[str]) -> str:
    known_block = "\n".join(f"- {k}" for k in known) if known else "(none yet)"
    focus = (focus or "").strip()
    return (
        f"Target region: {region}\n"
        f"Category: {category}: {CATEGORY_BRIEFS[category]}\n"
        f"Today's date: {today}\n"
        + (f"Focus notes from the person who started this scan:\n{focus}\n" if focus else "")
        + f"\nAlready in the catalogue for this category:\n{known_block}\n\n"
        f"Budget: save at most {settings.max_opportunities_per_task} opportunities in "
        f"this task. Save each one as soon as it is verified, then stop and summarize "
        f"what you saved and what you skipped."
    )


async def run_discover_opportunities(
    session,
    task,
    run,
    on_event=None,
    resume_messages=None,
    on_checkpoint=None,
):
    category = category_of(task)
    region = (run.region or "").strip() or settings.opportunity_default_region
    focus = run.interest_statement if run.interest_statement != "-" else ""
    message = user_message(
        region=region,
        category=category,
        focus=focus,
        today=opp_service.today().isoformat(),
        known=await _known(session, category),
    )
    ctx = ToolContext(session=session, run=run)
    return await run_agent_task(
        DISCOVER_OPPORTUNITIES_SYSTEM_PROMPT,
        message,
        ctx,
        on_event=on_event,
        resume_messages=resume_messages,
        on_checkpoint=on_checkpoint,
        progress_tools={"save_opportunity"},
        task_type=TASK_TYPE,
    )
