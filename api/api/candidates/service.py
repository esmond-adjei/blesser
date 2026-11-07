"""Candidate service: ranked shortlist, review records, review gate."""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.candidates import models as candidate_models
from api.core.exceptions import BadRequestError, NotFoundError
from api.index import sync as index_sync
from api.outreach import models as outreach_models
from api.prospects import models as prospect_models
from api.runs.models import Run
from api.runs.models import status_str as _status_str
from api.runs.notify import notify_candidates, notify_drafts
from api.runs.service import get_run_or_404
from api.runs.task_service import find_inflight_draft_tasks


def validate_candidate_filter(status: str | None, sort: str) -> None:
    if sort not in ("score", "recent"):
        raise BadRequestError("sort must be 'score' or 'recent'")
    if status is not None and status not in {
        s.value for s in candidate_models.CandidateStatus
    }:
        raise BadRequestError(f"Unknown candidate status: {status}")


async def get_candidate_or_404(
    session: AsyncSession, candidate_id: str, user_id: str
) -> candidate_models.CandidateScore:
    c = (
        (
            await session.execute(
                select(candidate_models.CandidateScore).where(
                    candidate_models.CandidateScore.id == candidate_id,
                    candidate_models.CandidateScore.user_id == user_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if not c:
        raise NotFoundError("Candidate not found")
    return c


async def list_candidates(
    session: AsyncSession,
    user_id: str,
    run_id: str,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort: str = "score",
) -> tuple[list[dict], int]:
    """Returns (items, total pre-page)."""
    validate_candidate_filter(status, sort)
    await get_run_or_404(session, run_id, user_id)
    filters = [
        candidate_models.CandidateScore.run_id == run_id,
        candidate_models.CandidateScore.user_id == user_id,
    ]
    if status is not None:
        filters.append(
            candidate_models.CandidateScore.status
            == candidate_models.CandidateStatus(status)
        )
    total = (
        await session.execute(
            select(func.count())
            .select_from(candidate_models.CandidateScore)
            .where(*filters)
        )
    ).scalar() or 0
    order = (
        candidate_models.CandidateScore.similarity_score.desc()
        if sort == "score"
        else candidate_models.CandidateScore.created_at.desc()
    )
    result = await session.execute(
        select(candidate_models.CandidateScore)
        .where(*filters)
        .order_by(order)
        .offset(offset)
        .limit(limit)
        .options(selectinload(candidate_models.CandidateScore.draft))
    )
    candidates = result.scalars().all()
    return await _candidate_out_batch(session, user_id, list(candidates)), total


async def search_candidates(
    session: AsyncSession,
    user_id: str,
    *,
    q: str | None = None,
    run_ids: list[str] | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort: str = "score",
) -> tuple[list[dict], int]:
    """Cross-run search over one account's runs. `q` matches professor, school or
    program names; unknown `run_ids` match nothing. Returns (items, total pre-page)."""
    validate_candidate_filter(status, sort)
    filters = [candidate_models.CandidateScore.user_id == user_id]
    if run_ids:
        filters.append(candidate_models.CandidateScore.run_id.in_(run_ids))
    if status is not None:
        filters.append(
            candidate_models.CandidateScore.status
            == candidate_models.CandidateStatus(status)
        )
    needle = (q or "").strip()
    if needle:
        like = f"%{needle}%"
        filters.append(
            (prospect_models.Professor.name.ilike(like))
            | (prospect_models.School.name.ilike(like))
            | (prospect_models.Program.name.ilike(like))
        )
    joined = (
        select(candidate_models.CandidateScore)
        .join(
            prospect_models.Professor,
            prospect_models.Professor.id
            == candidate_models.CandidateScore.professor_id,
        )
        .join(
            prospect_models.Program,
            prospect_models.Program.id == prospect_models.Professor.program_id,
        )
        .join(
            prospect_models.School,
            prospect_models.School.id == prospect_models.Program.school_id,
        )
        .where(*filters)
    )
    total = (
        await session.execute(select(func.count()).select_from(joined.subquery()))
    ).scalar() or 0
    order = (
        candidate_models.CandidateScore.similarity_score.desc()
        if sort == "score"
        else candidate_models.CandidateScore.created_at.desc()
    )
    result = await session.execute(
        joined.order_by(order)
        .offset(offset)
        .limit(limit)
        .options(selectinload(candidate_models.CandidateScore.draft))
    )
    candidates = result.scalars().all()
    return await _candidate_out_batch(session, user_id, list(candidates)), total


async def _candidate_out_batch(
    session: AsyncSession, user_id: str, candidates: list
) -> list[dict]:
    """Hydrate candidate rows into API dicts, batched. Every hop is owner-filtered
    so a crafted id can never pull another account's graph."""

    professor_ids = list({c.professor_id for c in candidates})
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
    prof_map = {p.id: p for p in professors}
    program_ids = list({p.program_id for p in professors})
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
        if program_ids
        else []
    )
    prog_map = {p.id: p for p in programs}
    school_ids = list({p.school_id for p in programs})
    schools = (
        (
            await session.execute(
                select(prospect_models.School).where(
                    prospect_models.School.id.in_(school_ids),
                    prospect_models.School.user_id == user_id,
                )
            )
        )
        .scalars()
        .all()
        if school_ids
        else []
    )
    school_map = {s.id: s for s in schools}

    draft_counts: dict[str, int] = {}
    if candidates:
        draft_rows = (
            await session.execute(
                select(outreach_models.EmailDraft.candidate_id, func.count())
                .where(
                    outreach_models.EmailDraft.candidate_id.in_(
                        [c.id for c in candidates]
                    )
                )
                .group_by(outreach_models.EmailDraft.candidate_id)
            )
        ).all()
        draft_counts = {cid: count for cid, count in draft_rows}

    out = []
    for c in candidates:
        professor = prof_map[c.professor_id]
        program = prog_map[professor.program_id]
        school = school_map[program.school_id]
        out.append(
            {
                "id": c.id,
                "run_id": c.run_id,
                "professor_id": professor.id,
                "program_id": program.id,
                "school_id": school.id,
                "professor_name": professor.name,
                "school_name": school.name,
                "program_name": program.name,
                "professor_photo_url": professor.photo_url,
                "school_image_url": school.image_url,
                "similarity_score": c.similarity_score,
                "rationale": c.rationale,
                "status": c.status,
                "draft_id": c.draft.id if c.draft else None,
                "draft_subject": c.draft.subject if c.draft else None,
                "draft_body": c.draft.body if c.draft else None,
                "draft_created_at": c.draft.created_at if c.draft else None,
                "draft_count": draft_counts.get(c.id, 0),
            }
        )
    return out


async def get_candidate_detail(
    session: AsyncSession, user_id: str, candidate_id: str
) -> dict:
    """Full review record, plus the in-flight draft task so the UI can disable
    Request-draft."""
    c = await get_candidate_or_404(session, candidate_id, user_id)
    # Async sessions can't lazy-load on access.
    await session.refresh(c, ["draft"])
    professor = await session.get(prospect_models.Professor, c.professor_id)
    if professor is None or professor.user_id != user_id:
        raise NotFoundError("Candidate not found")
    await session.refresh(professor, ["papers"])
    program = await session.get(prospect_models.Program, professor.program_id)
    if program is None or program.user_id != user_id:
        raise NotFoundError("Candidate not found")
    school = await session.get(prospect_models.School, program.school_id)
    if school is None or school.user_id != user_id:
        raise NotFoundError("Candidate not found")
    # In-flight draft task only: none means the Request-draft button re-enables.
    draft_task = (await find_inflight_draft_tasks(session, user_id, [c.id])).get(c.id)
    run = await get_run_or_404(session, c.run_id, user_id)
    CS = candidate_models.CandidateScore
    siblings = (
        await session.execute(
            select(CS.id, CS.run_id, CS.similarity_score, CS.status, Run.interest_statement)
            .join(Run, Run.id == CS.run_id)
            .where(CS.user_id == user_id, CS.professor_id == professor.id)
            .order_by(CS.similarity_score.desc().nulls_last())
        )
    ).all()
    return {
        "id": c.id,
        "run_id": c.run_id,
        "interest": run.interest_statement or None,
        "professor_id": professor.id,
        "program_id": program.id,
        "school_id": school.id,
        "professor_name": professor.name,
        "school_name": school.name,
        "program_name": program.name,
        "professor_photo_url": professor.photo_url,
        "school_image_url": school.image_url,
        "similarity_score": c.similarity_score,
        "rationale": c.rationale,
        "status": c.status,
        "papers": [
            {"id": p.id, "title": p.title, "abstract": p.abstract, "year": p.year, "url": p.url,
             "citations": p.citations, "publication_type": p.publication_type, "coauthors": p.coauthors or []}
            for p in professor.papers
        ],
        "draft_id": c.draft.id if c.draft else None,
        "draft_subject": c.draft.subject if c.draft else None,
        "draft_body": c.draft.body if c.draft else None,
        "draft_created_at": c.draft.created_at if c.draft else None,
        "draft_task_id": draft_task.id if draft_task is not None else None,
        "draft_task_status": _status_str(draft_task.status)
        if draft_task is not None
        else None,
        "matches": [
            {"id": m.id, "run_id": m.run_id, "similarity_score": m.similarity_score,
             "status": _status_str(m.status), "interest": m.interest_statement or None}
            for m in siblings
        ],
    }


async def delete_candidate(
    session: AsyncSession, user_id: str, candidate_id: str
) -> dict:
    """Discard a candidate and its draft; papers stay with the professor."""
    c = await get_candidate_or_404(session, candidate_id, user_id)
    await session.execute(
        delete(outreach_models.EmailDraft).where(
            outreach_models.EmailDraft.candidate_id == c.id,
            outreach_models.EmailDraft.user_id == user_id,
        )
    )
    await session.execute(
        delete(candidate_models.CandidateScore).where(
            candidate_models.CandidateScore.id == c.id
        )
    )
    await notify_candidates(session, c.run_id)
    await notify_drafts(session, c.run_id)
    await session.commit()
    return {"status": "deleted"}


def _apply_review(candidate: candidate_models.CandidateScore, approved: bool) -> None:
    candidate.status = (
        candidate_models.CandidateStatus.approved
        if approved
        else candidate_models.CandidateStatus.rejected
    )


async def review_candidate(
    session: AsyncSession, user_id: str, candidate_id: str, approved: bool
) -> dict:
    """Human-in-the-loop gate. Approving only marks the draft reviewed: sending is
    intentionally manual (see the README)."""
    candidate = await get_candidate_or_404(session, candidate_id, user_id)
    _apply_review(candidate, approved)
    await index_sync.sync_candidate_id(session, candidate.id)
    await notify_candidates(session, candidate.run_id)
    await session.commit()
    return {"status": _status_str(candidate.status)}


#: Statuses a person (or Gradis) may set by hand; pipeline stages are not offered.
EDITABLE_STATUSES = frozenset({"scored", "approved", "rejected", "sent"})


async def update_candidate(
    session: AsyncSession, user_id: str, candidate_id: str, data: dict
) -> dict:
    """Edit review status and/or rationale. The fit score is never editable."""
    candidate = await get_candidate_or_404(session, candidate_id, user_id)
    if "status" in data and data["status"] is not None:
        status = str(data["status"]).strip().lower()
        if status not in EDITABLE_STATUSES:
            raise BadRequestError(
                f"Status must be one of {', '.join(sorted(EDITABLE_STATUSES))}."
            )
        candidate.status = candidate_models.CandidateStatus(status)
    if "rationale" in data and data["rationale"] is not None:
        rationale = str(data["rationale"]).strip()
        if not rationale:
            raise BadRequestError("The rationale can't be empty.")
        candidate.rationale = rationale
    await index_sync.sync_candidate_id(session, candidate.id)
    await notify_candidates(session, candidate.run_id)
    await session.commit()
    return await get_candidate_detail(session, user_id, candidate_id)


async def review_bulk(
    session: AsyncSession, user_id: str, run_id: str, reviews: list[dict]
) -> dict:
    """Same per-item semantics as review_candidate; never sends anything."""
    await get_run_or_404(session, run_id, user_id)
    parsed: list[tuple[str, bool]] = []
    for item in reviews:
        if isinstance(item, dict):
            parsed.append((item["candidate_id"], item["approved"]))
        else:
            parsed.append((item.candidate_id, item.approved))  # type: ignore[union-attr]
    ids = [cid for cid, _ in parsed]
    found: dict[str, candidate_models.CandidateScore] = {}
    if ids:
        rows = (
            (
                await session.execute(
                    select(candidate_models.CandidateScore).where(
                        candidate_models.CandidateScore.id.in_(ids),
                        candidate_models.CandidateScore.run_id == run_id,
                        candidate_models.CandidateScore.user_id == user_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        found = {c.id: c for c in rows}
    approved_by_id = {cid: approved for cid, approved in parsed}
    updated, skipped = [], []
    for cid in ids:
        candidate = found.get(cid)
        if candidate is None:
            skipped.append({"id": cid, "reason": "not found in run"})
            continue
        _apply_review(candidate, approved_by_id[cid])
        await index_sync.sync_candidate_id(session, candidate.id)
        updated.append(cid)
    if updated:
        await notify_candidates(session, run_id)
    await session.commit()
    return {"updated": updated, "skipped": skipped}
