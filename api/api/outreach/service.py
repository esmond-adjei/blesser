"""Outreach service: draft queueing, outbox, editing, discard."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.candidates import models as candidate_models
from api.candidates.service import get_candidate_or_404
from api.core.exceptions import ConflictError, NotFoundError
from api.index import sync as index_sync
from api.outreach import models as outreach_models
from api.prospects import models as prospect_models
from api.runs import models as run_models
from api.runs.lifecycle import note_work_enqueued
from api.runs.notify import notify_candidates, notify_drafts
from api.runs.service import get_run_or_404
from api.runs.task_service import find_inflight_draft_tasks


async def get_draft_or_404(
    session: AsyncSession, draft_id: str, user_id: str
) -> outreach_models.EmailDraft:
    draft = (
        (
            await session.execute(
                select(outreach_models.EmailDraft).where(
                    outreach_models.EmailDraft.id == draft_id,
                    outreach_models.EmailDraft.user_id == user_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if not draft:
        raise NotFoundError("Draft not found")
    return draft


def _draft_task_target_name(
    professor_name: str | None, school_name: str | None
) -> str | None:
    """Human label for a draft_email task: 'professor, school'."""
    parts = [p for p in (professor_name, school_name) if p]
    return ", ".join(parts) if parts else None


async def _draft_task_target_names(
    session: AsyncSession, user_id: str, candidates: list[candidate_models.CandidateScore]
) -> dict[str, str | None]:
    if not candidates:
        return {}
    professors = (
        (
            await session.execute(
                select(prospect_models.Professor).where(
                    prospect_models.Professor.id.in_(
                        list({c.professor_id for c in candidates})
                    ),
                    prospect_models.Professor.user_id == user_id,
                )
            )
        )
        .scalars()
        .all()
    )
    prof_map = {p.id: p for p in professors}
    programs = (
        (
            await session.execute(
                select(prospect_models.Program).where(
                    prospect_models.Program.id.in_(
                        list({p.program_id for p in professors})
                    ),
                    prospect_models.Program.user_id == user_id,
                )
            )
        )
        .scalars()
        .all()
        if professors
        else []
    )
    prog_map = {p.id: p for p in programs}
    schools = (
        (
            await session.execute(
                select(prospect_models.School).where(
                    prospect_models.School.id.in_(list({p.school_id for p in programs})),
                    prospect_models.School.user_id == user_id,
                )
            )
        )
        .scalars()
        .all()
        if programs
        else []
    )
    school_map = {s.id: s for s in schools}
    labels: dict[str, str | None] = {}
    for c in candidates:
        prof = prof_map.get(c.professor_id)
        prog = prog_map.get(prof.program_id) if prof is not None else None
        school = school_map.get(prog.school_id) if prog is not None else None
        labels[c.id] = _draft_task_target_name(
            prof.name if prof is not None else None,
            school.name if school is not None else None,
        )
    return labels


async def request_draft(session: AsyncSession, user_id: str, candidate_id: str) -> dict:
    candidate = await get_candidate_or_404(session, candidate_id, user_id)
    inflight = (await find_inflight_draft_tasks(session, user_id, [candidate.id])).get(
        candidate.id
    )
    if inflight is not None:
        raise ConflictError(
            "Draft already in progress for this candidate",
            {"task_id": inflight.id},
        )
    professor = await session.get(prospect_models.Professor, candidate.professor_id)
    program = (
        await session.get(prospect_models.Program, professor.program_id)
        if professor is not None and professor.user_id == user_id
        else None
    )
    school = (
        await session.get(prospect_models.School, program.school_id)
        if program is not None and program.user_id == user_id
        else None
    )
    session.add(
        run_models.ResearchTask(
            run_id=candidate.run_id,
            user_id=candidate.user_id,
            task_type="draft_email",
            target_id=candidate.id,
            target_name=_draft_task_target_name(
                professor.name if professor is not None else None,
                school.name if school is not None else None,
            ),
        )
    )
    await note_work_enqueued(session, candidate.run_id)
    await session.commit()
    return {"status": "queued"}


async def request_drafts(
    session: AsyncSession, user_id: str, run_id: str, candidate_ids: list[str]
) -> dict:
    """Unknown ids and ids from other runs are reported as skipped, never fail the batch."""
    run = await get_run_or_404(session, run_id, user_id)
    found: dict[str, candidate_models.CandidateScore] = {}
    if candidate_ids:
        rows = (
            (
                await session.execute(
                    select(candidate_models.CandidateScore).where(
                        candidate_models.CandidateScore.id.in_(candidate_ids),
                        candidate_models.CandidateScore.run_id == run_id,
                        candidate_models.CandidateScore.user_id == user_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        found = {c.id: c for c in rows}
    queued, skipped = [], []
    inflight = await find_inflight_draft_tasks(session, user_id, list(found))
    labels = await _draft_task_target_names(session, user_id, list(found.values()))
    seen: set[str] = set()
    for candidate_id in candidate_ids:
        candidate = found.get(candidate_id)
        if candidate is None:
            skipped.append({"id": candidate_id, "reason": "not found in run"})
            continue
        if candidate_id in seen:
            skipped.append(
                {"id": candidate_id, "reason": "duplicate in request", "task_id": None}
            )
            continue
        existing = inflight.get(candidate_id)
        if existing is not None:
            skipped.append(
                {
                    "id": candidate_id,
                    "reason": "draft already in progress",
                    "task_id": existing.id,
                }
            )
            continue
        seen.add(candidate_id)
        session.add(
            run_models.ResearchTask(
                run_id=run_id,
                user_id=run.user_id,
                task_type="draft_email",
                target_id=candidate.id,
                target_name=labels.get(candidate_id),
            )
        )
        queued.append(candidate_id)
    if queued:
        await note_work_enqueued(session, run_id)
    await session.commit()
    return {"queued": queued, "skipped": skipped}


async def list_drafts(session: AsyncSession, user_id: str, run_id: str) -> list[dict]:
    await get_run_or_404(session, run_id, user_id)
    candidate_ids = [
        row[0]
        for row in (
            await session.execute(
                select(candidate_models.CandidateScore.id).where(
                    candidate_models.CandidateScore.run_id == run_id,
                    candidate_models.CandidateScore.user_id == user_id,
                )
            )
        ).all()
    ]
    if not candidate_ids:
        return []
    drafts = (
        (
            await session.execute(
                select(outreach_models.EmailDraft)
                .where(
                    outreach_models.EmailDraft.candidate_id.in_(candidate_ids),
                    outreach_models.EmailDraft.user_id == user_id,
                )
                .order_by(outreach_models.EmailDraft.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    candidate_map: dict[str, candidate_models.CandidateScore] = {}
    if drafts:
        rows = (
            (
                await session.execute(
                    select(candidate_models.CandidateScore).where(
                        candidate_models.CandidateScore.id.in_(
                            [d.candidate_id for d in drafts]
                        ),
                        candidate_models.CandidateScore.user_id == user_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        candidate_map = {c.id: c for c in rows}
        professor_ids = list({c.professor_id for c in rows})
        professors = (
            (
                await session.execute(
                    select(prospect_models.Professor).where(
                        prospect_models.Professor.id.in_(professor_ids),
                        prospect_models.Professor.user_id == user_id,
                    )
                )
            )
            .scalars()
            .all()
            if professor_ids
            else []
        )
        professor_map = {p.id: p for p in professors}
    else:
        professor_map = {}
    places = await _places(session, user_id, list(professor_map.values()))

    out = []
    for draft in drafts:
        candidate = candidate_map[draft.candidate_id]
        professor = professor_map[candidate.professor_id]
        out.append(
            {
                "id": draft.id,
                "candidate_id": draft.candidate_id,
                "professor_name": professor.name,
                **_recipient(professor, places),
                "candidate_status": candidate.status,
                "similarity_score": candidate.similarity_score,
                "rationale": candidate.rationale,
                "subject": draft.subject,
                "body": draft.body,
                "created_at": draft.created_at,
            }
        )
    return out


async def list_candidate_drafts(
    session: AsyncSession, user_id: str, candidate_id: str
) -> list[dict]:
    """Every draft for one candidate, newest first (each save inserts a row)."""
    await get_candidate_or_404(session, candidate_id, user_id)
    drafts = (
        (
            await session.execute(
                select(outreach_models.EmailDraft)
                .where(
                    outreach_models.EmailDraft.candidate_id == candidate_id,
                    outreach_models.EmailDraft.user_id == user_id,
                )
                .order_by(outreach_models.EmailDraft.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [await draft_out(session, user_id, d) for d in drafts]


async def _places(session: AsyncSession, user_id: str, professors: list) -> dict:
    """{program_id: (program name, school name)}, owner-filtered at every hop."""
    program_ids = list({p.program_id for p in professors})
    if not program_ids:
        return {}
    programs = (
        (
            await session.execute(
                select(prospect_models.Program).where(
                    prospect_models.Program.id.in_(program_ids),
                    prospect_models.Program.user_id == user_id,
                )
            )
        )
        .scalars()
        .all()
    )
    school_ids = list({p.school_id for p in programs})
    schools = {
        s.id: s.name
        for s in (
            await session.execute(
                select(prospect_models.School).where(
                    prospect_models.School.id.in_(school_ids),
                    prospect_models.School.user_id == user_id,
                )
            )
        ).scalars()
    }
    return {p.id: (p.name, schools.get(p.school_id)) for p in programs}


def _recipient(professor, places: dict) -> dict:
    """Who a draft is addressed to, for the email card."""
    program_name, school_name = places.get(professor.program_id, (None, None))
    return {
        "professor_email": professor.email,
        "professor_photo_url": professor.photo_url,
        "school_name": school_name,
        "program_name": program_name,
    }


async def draft_out(
    session: AsyncSession, user_id: str, draft: outreach_models.EmailDraft
) -> dict:
    candidate = await get_candidate_or_404(session, draft.candidate_id, user_id)
    professor = await session.get(prospect_models.Professor, candidate.professor_id)
    if professor is None or professor.user_id != user_id:
        raise NotFoundError("Candidate not found")
    places = await _places(session, user_id, [professor])
    return {
        "id": draft.id,
        "candidate_id": draft.candidate_id,
        "professor_name": professor.name,
        **_recipient(professor, places),
        "candidate_status": candidate.status,
        "similarity_score": candidate.similarity_score,
        "rationale": candidate.rationale,
        "subject": draft.subject,
        "body": draft.body,
        "created_at": draft.created_at,
    }


DRAFT_MUTABLE = {"subject", "body"}


async def update_draft(session: AsyncSession, user_id: str, draft_id: str, data: dict) -> dict:
    draft = await get_draft_or_404(session, draft_id, user_id)
    for key, value in data.items():
        if key in DRAFT_MUTABLE:
            setattr(draft, key, value)
    candidate = await session.get(candidate_models.CandidateScore, draft.candidate_id)
    if candidate is not None and candidate.user_id != user_id:
        raise NotFoundError("Draft not found")
    if candidate is not None:
        await notify_drafts(session, candidate.run_id)
    await session.commit()
    return await draft_out(session, user_id, draft)


async def delete_draft(session: AsyncSession, user_id: str, draft_id: str) -> dict:
    """A candidate left in `drafted` status falls back to `scored`."""
    draft = await get_draft_or_404(session, draft_id, user_id)
    candidate = await session.get(candidate_models.CandidateScore, draft.candidate_id)
    if candidate is not None and candidate.user_id != user_id:
        raise NotFoundError("Draft not found")
    await session.execute(
        delete(outreach_models.EmailDraft).where(
            outreach_models.EmailDraft.id == draft.id
        )
    )
    if candidate is not None and (
        run_models.status_str(candidate.status)
        == candidate_models.CandidateStatus.drafted.value
    ):
        candidate.status = candidate_models.CandidateStatus.scored
    if candidate is not None:
        await index_sync.sync_candidate_id(session, candidate.id)
        await notify_drafts(session, candidate.run_id)
        await notify_candidates(session, candidate.run_id)
    await session.commit()
    return {"status": "deleted"}
