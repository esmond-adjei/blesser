"""Run graph traversal, the reviewed-work guard, and bottom-up deletes."""

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.candidates import models as candidate_models
from api.core.exceptions import ConflictError
from api.outreach import models as outreach_models
from api.prospects import models as prospect_models
from api.runs import models as run_models
from api.runs.service import get_run_or_404


async def _ids_in(session: AsyncSession, column, criterion) -> list[str]:
    if criterion is None:
        return []
    rows = await session.execute(select(column).where(criterion))
    return [row[0] for row in rows.all()]


async def _schools_only_this_run_uses(session: AsyncSession, run_id: str) -> list[str]:
    """Schools no other run links to or has a candidate at; shared schools stay."""
    link = prospect_models.RunSchool
    other_link = (
        select(link.school_id)
        .where(link.school_id == prospect_models.School.id, link.run_id != run_id)
        .exists()
    )
    other_candidate = (
        select(candidate_models.CandidateScore.id)
        .join(
            prospect_models.Professor,
            prospect_models.Professor.id == candidate_models.CandidateScore.professor_id,
        )
        .join(
            prospect_models.Program,
            prospect_models.Program.id == prospect_models.Professor.program_id,
        )
        .where(
            prospect_models.Program.school_id == prospect_models.School.id,
            candidate_models.CandidateScore.run_id != run_id,
        )
        .exists()
    )
    linked = select(link.school_id).where(link.run_id == run_id)
    return await _ids_in(
        session,
        prospect_models.School.id,
        prospect_models.School.id.in_(linked) & ~other_link & ~other_candidate,
    )


async def subtree_ids(session: AsyncSession, run_id: str) -> dict[str, list[str]]:
    """Every id a run's deletion removes, top-down."""
    school_ids = await _schools_only_this_run_uses(session, run_id)
    program_ids = (
        await _ids_in(
            session,
            prospect_models.Program.id,
            prospect_models.Program.school_id.in_(school_ids),
        )
        if school_ids
        else []
    )
    professor_ids = (
        await _ids_in(
            session,
            prospect_models.Professor.id,
            prospect_models.Professor.program_id.in_(program_ids),
        )
        if program_ids
        else []
    )
    paper_ids = (
        await _ids_in(
            session,
            prospect_models.Paper.id,
            prospect_models.Paper.professor_id.in_(professor_ids),
        )
        if professor_ids
        else []
    )
    candidate_ids = await _ids_in(
        session,
        candidate_models.CandidateScore.id,
        candidate_models.CandidateScore.run_id == run_id,
    )
    draft_ids = (
        await _ids_in(
            session,
            outreach_models.EmailDraft.id,
            outreach_models.EmailDraft.candidate_id.in_(candidate_ids),
        )
        if candidate_ids
        else []
    )
    task_ids = await _ids_in(
        session,
        run_models.ResearchTask.id,
        run_models.ResearchTask.run_id == run_id,
    )
    return {
        "schools": school_ids,
        "programs": program_ids,
        "professors": professor_ids,
        "papers": paper_ids,
        "candidates": candidate_ids,
        "drafts": draft_ids,
        "tasks": task_ids,
    }


async def reviewed_professor_ids(
    session: AsyncSession, professor_ids: list[str]
) -> set[str]:
    """Professors with a candidate row; deleting them would orphan reviewed work."""
    if not professor_ids:
        return set()
    rows = (
        await session.execute(
            select(candidate_models.CandidateScore.professor_id).where(
                candidate_models.CandidateScore.professor_id.in_(professor_ids)
            )
        )
    ).all()
    return {row[0] for row in rows}


async def blocking_candidate_count(
    session: AsyncSession, professor_ids: list[str]
) -> int:
    if not professor_ids:
        return 0
    return (
        await session.execute(
            select(func.count())
            .select_from(candidate_models.CandidateScore)
            .where(candidate_models.CandidateScore.professor_id.in_(professor_ids))
        )
    ).scalar() or 0


async def guard_no_reviewed(
    session: AsyncSession, what: str, professor_ids: list[str]
) -> None:
    """Refuse with 409 when any professor below has reviewed work."""
    reviewed = await reviewed_professor_ids(session, professor_ids)
    if reviewed:
        count = await blocking_candidate_count(session, professor_ids)
        raise ConflictError(
            f"{what} has {count} reviewed candidate(s); delete them first",
            {"candidates": count},
        )


async def delete_preview(session: AsyncSession, user_id: str, run_id: str) -> dict:
    """Per-table row counts deleting this run would remove."""
    await get_run_or_404(session, run_id, user_id)
    ids = await subtree_ids(session, run_id)
    counts = {key: len(value) for key, value in ids.items()}
    counts["tool_calls"] = (
        (
            await session.execute(
                select(func.count())
                .select_from(run_models.ToolCallLog)
                .where(run_models.ToolCallLog.task_id.in_(ids["tasks"]))
            )
        ).scalar()
        or 0
        if ids["tasks"]
        else 0
    )
    return counts


async def delete_run(session: AsyncSession, user_id: str, run_id: str) -> dict:
    """Explicit bottom-up deletes: async sessions can't cascade-delete unloaded relationships."""
    run = await get_run_or_404(session, run_id, user_id)

    ids = await subtree_ids(session, run_id)
    task_ids = ids["tasks"]
    school_ids = ids["schools"]
    program_ids = ids["programs"]
    professor_ids = ids["professors"]
    candidate_ids = ids["candidates"]

    if task_ids:
        await session.execute(
            delete(run_models.ToolCallLog).where(
                run_models.ToolCallLog.task_id.in_(task_ids)
            )
        )
        await session.execute(
            delete(run_models.ResearchTask).where(
                run_models.ResearchTask.id.in_(task_ids)
            )
        )
    if candidate_ids:
        await session.execute(
            delete(outreach_models.EmailDraft).where(
                outreach_models.EmailDraft.candidate_id.in_(candidate_ids)
            )
        )
        await session.execute(
            delete(candidate_models.CandidateScore).where(
                candidate_models.CandidateScore.id.in_(candidate_ids)
            )
        )
    if professor_ids:
        await session.execute(
            delete(prospect_models.Paper).where(
                prospect_models.Paper.professor_id.in_(professor_ids)
            )
        )
        await session.execute(
            delete(prospect_models.Professor).where(
                prospect_models.Professor.id.in_(professor_ids)
            )
        )
    if program_ids:
        await session.execute(
            delete(prospect_models.Program).where(
                prospect_models.Program.id.in_(program_ids)
            )
        )
    await session.execute(
        delete(prospect_models.RunSchool).where(
            prospect_models.RunSchool.run_id == run.id
        )
    )
    if school_ids:
        await session.execute(
            delete(prospect_models.School).where(
                prospect_models.School.id.in_(school_ids)
            )
        )
    await session.execute(
        update(prospect_models.School)
        .where(prospect_models.School.run_id == run.id)
        .values(run_id=None)
    )
    await session.execute(delete(run_models.Run).where(run_models.Run.id == run.id))
    await session.commit()
    return {"status": "deleted"}
