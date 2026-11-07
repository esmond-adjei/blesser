"""Outreach tool implementations: email drafts (never sent)."""

from api.agent.tools.budgets import check_task_budget
from api.agent.tools.context import ToolContext
from api.candidates import models as candidate_models
from api.index import sync as index_sync
from api.outreach import draft_check
from api.outreach import models as outreach_models
from api.prospects import models as prospect_models
from api.runs.notify import notify_candidates, notify_drafts


async def _school_name(session, program_id: str) -> str | None:
    program = await session.get(prospect_models.Program, program_id)
    if program is None:
        return None
    school = await session.get(prospect_models.School, program.school_id)
    return school.name if school is not None else None


async def handle_save_email_draft(tool_input: dict, ctx: ToolContext) -> dict:
    refusal = check_task_budget(ctx, "drafts")
    if refusal is not None:
        return refusal
    candidate_id = tool_input.get("candidate_id") or ctx.last_candidate_id
    if not candidate_id:
        return {"error": "No candidate_id given and none inferred from context."}

    candidate = await ctx.session.get(candidate_models.CandidateScore, candidate_id)
    if (
        candidate is None
        or candidate.run_id != ctx.run.id
        or candidate.user_id != ctx.user_id
    ):
        return {"error": "Candidate not found in this run."}

    # Research-agent drafts must cite a stored paper; Gradis drafts (unmetered)
    # keep only the length and placeholder checks.
    titles = None
    known_facts = None
    targets = ""
    context = ""
    if getattr(ctx, "metered", True):
        known_facts = draft_check.known_facts_for(ctx.run)
        professor = await ctx.session.get(
            prospect_models.Professor, candidate.professor_id
        )
        if professor is not None:
            await ctx.session.refresh(professor, ["papers"])
            targets = draft_check.target_names_for(
                await _school_name(ctx.session, professor.program_id),
                professor.name,
                professor.lab_name,
            )
        titles = [p.title for p in professor.papers] if professor is not None else []
        # Names from the brief's professor context (tools, venues) are not inventions.
        context = " ".join(
            [candidate.rationale or ""]
            + [p.abstract or "" for p in (professor.papers if professor else [])]
        )
    error = draft_check.verify_draft(
        tool_input.get("subject") or "",
        tool_input.get("body") or "",
        titles,
        known_facts,
        targets,
        context,
    )
    if error is not None:
        return {"error": error}

    draft = outreach_models.EmailDraft(
        candidate_id=candidate_id,
        user_id=ctx.user_id,
        subject=tool_input["subject"],
        body=tool_input["body"],
    )
    ctx.session.add(draft)

    candidate.status = candidate_models.CandidateStatus.drafted
    await index_sync.sync_candidate_id(ctx.session, candidate.id)

    await notify_drafts(ctx.session, ctx.run.id)
    await notify_candidates(ctx.session, ctx.run.id)
    await ctx.session.commit()
    ctx.drafts_saved += 1
    return {"draft_id": draft.id, "status": "drafted"}
