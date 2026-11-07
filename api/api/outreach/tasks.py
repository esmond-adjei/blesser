"""Outreach task handlers: email drafting."""

from api.agent.orchestrator import run_agent_task
from api.agent.tools.context import ToolContext
from api.core.config import settings
from api.outreach.prompts import DRAFT_EMAIL_SYSTEM_PROMPT

DEGREE_WORDS = {"phd": "PhD", "masters": "master's", "either": "graduate"}


def _known_facts(run) -> str:
    """Everything the draft may state about the student; anything else must stay a
    [bracketed placeholder]."""
    degree = DEGREE_WORDS.get((run.degree_level or "").lower(), run.degree_level)
    facts = [
        f"- Seeking: {degree} admission"
        + (f" in {run.field}" if getattr(run, "field", None) else ""),
        f"- Research interests (their own words): {run.interest_statement}",
    ]
    return (
        "Known facts about the student (state nothing else about them):\n"
        + "\n".join(facts)
        + "\nUnknown (write as [bracketed placeholders] for the student to fill): "
        "their current degree and university, grades, publications, projects, "
        "and experience."
    )


async def run_draft_email(
    session,
    task,
    run,
    on_event=None,
    resume_messages=None,
    on_checkpoint=None,
):
    from api.candidates import models as candidate_models
    from api.prospects import models as prospect_models

    candidate = await session.get(candidate_models.CandidateScore, task.target_id)
    if candidate is None:
        raise RuntimeError(
            f"Candidate {task.target_id} not found for research task {task.id}"
        )
    if candidate.user_id != run.user_id:
        raise RuntimeError(f"Candidate {task.target_id} is not owned by run {run.id}")
    professor = await session.get(prospect_models.Professor, candidate.professor_id)
    if professor.user_id != run.user_id:
        raise RuntimeError(
            f"Professor {candidate.professor_id} is not owned by run {run.id}"
        )
    # Eager-load: async sessions raise MissingGreenlet on lazy access.
    await session.refresh(professor, ["papers"])
    papers = professor.papers

    user_message = (
        f"Professor: {professor.name}\n"
        f"Matched papers:\n"
        + "\n".join(
            f"- {p.title} ({p.year}): {p.abstract or 'no abstract'}" for p in papers
        )
        + f"\n\nWhy this is a match: {candidate.rationale}\n\n"
        + _known_facts(run)
        + "\n\n"
        f"candidate_id for save_email_draft: {candidate.id}\n\n"
        f"Budget: save at most {settings.max_drafts_per_task} drafts - make the "
        f"first one count, then stop."
    )
    ctx = ToolContext(session=session, run=run)
    ctx.last_candidate_id = candidate.id
    result = await run_agent_task(
        DRAFT_EMAIL_SYSTEM_PROMPT,
        user_message,
        ctx,
        on_event=on_event,
        resume_messages=resume_messages,
        on_checkpoint=on_checkpoint,
        progress_tools={"save_email_draft"},
        task_type="draft_email",
        small_model=True,
    )
    return result
