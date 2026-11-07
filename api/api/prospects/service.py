"""Prospect service: schools, programs, professors, discovery tree."""

import asyncio
import re
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.candidates import models as candidate_models
from api.candidates import scoring, verification
from api.core.config import settings
from api.core.exceptions import BadRequestError, NotFoundError
from api.core.textnorm import canonical_openalex_id, normalize_text
from api.index import sync as index_sync
from api.index.keys import person_key as name_key
from api.prospects import models as prospect_models
from api.prospects import school_links
from api.prospects.schemas import ProgramCreate, ProgramSeed
from api.runs import models as run_models
from api.runs.budgets import default_run_budgets
from api.runs.lifecycle import note_work_enqueued
from api.runs.removal import guard_no_reviewed
from api.runs.service import (
    cache_interest_embedding,
    get_run_or_404,
    validate_interest_document,
)


async def seed_run(
    session: AsyncSession,
    user_id: str,
    *,
    degree_level: str,
    interest_statement: str,
    interest_document_id: str | None = None,
    programs: Sequence[ProgramSeed | dict],
    region: str,
    field: str,
    max_programs: int | None = None,
    max_professors: int | None = None,
    max_professors_per_program: int | None = None,
    flow_id: str | None = None,
    llm_provider: str | None = None,
) -> run_models.Run:
    """Create a run from explicit programs, skipping discovery. Seeds bypass the
    program cap; unset budgets are stored as server defaults, never NULL."""
    if not programs:
        raise BadRequestError("programs must not be empty")
    seeds = [
        p if isinstance(p, ProgramSeed) else ProgramSeed.model_validate(p)
        for p in programs
    ]
    max_programs, max_professors, max_professors_per_program = default_run_budgets(
        max_programs, max_professors, max_professors_per_program
    )
    interest_document_id = await validate_interest_document(
        session, user_id, interest_document_id, interest_statement
    )
    run = run_models.Run(
        user_id=user_id,
        region=region,
        field=field,
        degree_level=degree_level,
        interest_statement=interest_statement,
        interest_document_id=interest_document_id,
        status="running",
        max_programs=max_programs,
        max_professors=max_professors,
        max_professors_per_program=max_professors_per_program,
        flow_id=flow_id,
        llm_provider=llm_provider,
    )
    session.add(run)
    await session.flush()

    await cache_interest_embedding(run)

    await school_links.lock_account(session, user_id)
    for p in seeds:
        # Seeds carry a department page, not a school homepage.
        school = await _account_school(
            session, run.id, user_id, name=p.school_name, country=p.school_country, website_url=None
        )
        program = await _account_program(
            session, school, name=p.program_name, department_url=p.department_url
        )
        if await school_links.program_in_run(session, run.id, program.id):
            continue
        session.add(
            run_models.ResearchTask(
                run_id=run.id,
                user_id=user_id,
                task_type="research_professor",
                target_id=program.id,
                target_name=school.name,
            )
        )
    await note_work_enqueued(session, run.id)
    await session.commit()
    return run


async def _account_school(
    session: AsyncSession,
    run_id: str,
    user_id: str,
    *,
    name: str,
    country: str | None,
    website_url: str | None,
) -> prospect_models.School:
    """Find or create the school, linked as a person's addition. Caller holds the save lock."""
    school = await school_links.find_school(
        session, user_id, name=name, website_url=website_url
    )
    if school is None:
        school = prospect_models.School(
            user_id=user_id,
            name=name,
            country=country,
            website_url=website_url,
            origin="user",
        )
        session.add(school)
        await session.flush()
    else:
        school_links.fill_school(school, country=country, website_url=website_url)
    await school_links.link_school(session, run_id, school, origin="user")
    return school


async def _account_program(
    session: AsyncSession,
    school: prospect_models.School,
    *,
    name: str,
    department_url: str | None,
) -> prospect_models.Program:
    """Find or create the programme by name or department page."""
    program = await school_links.find_program(
        session, school.id, name=name, department_url=department_url
    )
    if program is None:
        program = prospect_models.Program(
            school_id=school.id,
            user_id=school.user_id,
            name=name,
            department_url=department_url,
        )
        session.add(program)
        await session.flush()
    elif department_url and not program.department_url:
        program.department_url = department_url
    return program


async def _school_run_id(session: AsyncSession, school: prospect_models.School) -> str:
    """The latest run using the school, where added work is queued."""
    run_id = await school_links.latest_run_id(session, school.id)
    if run_id is None:
        raise BadRequestError("No run uses this school; add it to a run first.")
    return run_id


async def get_school_or_404(
    session: AsyncSession, school_id: str, user_id: str
) -> prospect_models.School:
    school = (
        (
            await session.execute(
                select(prospect_models.School).where(
                    prospect_models.School.id == school_id,
                    prospect_models.School.user_id == user_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if not school:
        raise NotFoundError("School not found")
    return school


async def get_program_or_404(
    session: AsyncSession, program_id: str, user_id: str
) -> prospect_models.Program:
    program = (
        (
            await session.execute(
                select(prospect_models.Program).where(
                    prospect_models.Program.id == program_id,
                    prospect_models.Program.user_id == user_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if not program:
        raise NotFoundError("Program not found")
    return program


async def get_professor_or_404(
    session: AsyncSession, professor_id: str, user_id: str
) -> prospect_models.Professor:
    professor = (
        (
            await session.execute(
                select(prospect_models.Professor).where(
                    prospect_models.Professor.id == professor_id,
                    prospect_models.Professor.user_id == user_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if not professor:
        raise NotFoundError("Professor not found")
    return professor


async def professor_counts(
    session: AsyncSession, user_id: str, program_ids: list[str]
) -> dict[str, int]:
    if not program_ids:
        return {}
    rows = (
        await session.execute(
            select(prospect_models.Professor.program_id, func.count())
            .where(
                prospect_models.Professor.program_id.in_(program_ids),
                prospect_models.Professor.user_id == user_id,
            )
            .group_by(prospect_models.Professor.program_id)
        )
    ).all()
    return {pid: count for pid, count in rows}


async def paper_counts(
    session: AsyncSession, user_id: str, professor_ids: list[str]
) -> dict[str, int]:
    if not professor_ids:
        return {}
    rows = (
        await session.execute(
            select(prospect_models.Paper.professor_id, func.count())
            .where(
                prospect_models.Paper.professor_id.in_(professor_ids),
                prospect_models.Paper.user_id == user_id,
            )
            .group_by(prospect_models.Paper.professor_id)
        )
    ).all()
    return {pid: count for pid, count in rows}


async def list_programs_tree(session: AsyncSession, user_id: str, run_id: str) -> list[dict]:
    """Schools with their programs and per-program professor counts."""
    await get_run_or_404(session, run_id, user_id)
    rows = (
        await session.execute(
            select(prospect_models.School, prospect_models.RunSchool.tier)
            .join(
                prospect_models.RunSchool,
                prospect_models.RunSchool.school_id == prospect_models.School.id,
            )
            .where(
                prospect_models.RunSchool.run_id == run_id,
                prospect_models.School.user_id == user_id,
            )
            .order_by(prospect_models.School.name)
        )
    ).all()
    schools = [row[0] for row in rows]
    tier_by_school = {row[0].id: row[1] for row in rows}
    school_ids = [s.id for s in schools]
    programs_by_school: dict[str, list] = {sid: [] for sid in school_ids}
    if school_ids:
        # A shared school lists every programme the account has there.
        all_programs = (
            (
                await session.execute(
                    select(prospect_models.Program)
                    .where(prospect_models.Program.school_id.in_(school_ids))
                    .order_by(prospect_models.Program.name)
                )
            )
            .scalars()
            .all()
        )
        for p in all_programs:
            programs_by_school.setdefault(p.school_id, []).append(p)
        counts = await professor_counts(session, user_id, [p.id for p in all_programs])
    else:
        counts = {}
    out = []
    for school in schools:
        program_outs = [
            {
                "id": p.id,
                "name": p.name,
                "department_url": p.department_url,
                "professors": counts.get(p.id, 0),
            }
            for p in programs_by_school.get(school.id, [])
        ]
        out.append(
            {
                "id": school.id,
                "name": school.name,
                "country": school.country,
                "website_url": school.website_url,
                "image_url": school.image_url,
                "tier": tier_by_school.get(school.id),
                "programs": program_outs,
            }
        )
    return out


async def create_school(
    session: AsyncSession,
    user_id: str,
    run_id: str,
    *,
    name: str,
    country: str | None,
    website_url: str | None,
    programs: Sequence[ProgramCreate | dict] | None = None,
) -> dict:
    """Each inline program also queues its ``research_professor`` task."""
    run = await get_run_or_404(session, run_id, user_id)
    # Only a school new to this run spends its allowance.
    await school_links.lock_account(session, run.user_id)
    existing = await school_links.find_school(
        session, run.user_id, name=name, website_url=website_url
    )
    linked = existing is not None and (
        await school_links.run_link(session, run.id, existing.id) is not None
    )
    added = await school_links.count_links(session, run.id, origin="user")
    if not linked and added >= settings.max_user_programs_per_run:
        raise BadRequestError(
            f"This run already has {added} schools you added "
            f"(limit {settings.max_user_programs_per_run}). Start a new run for more."
        )
    seeds = [
        p if isinstance(p, ProgramCreate) else ProgramCreate.model_validate(p)
        for p in (programs or [])
    ]
    school = await _account_school(
        session, run.id, run.user_id, name=name, country=country, website_url=website_url
    )
    programs_added = []
    for p in seeds:
        program = await _account_program(
            session, school, name=p.name, department_url=p.department_url
        )
        if not await school_links.program_in_run(session, run.id, program.id):
            session.add(
                run_models.ResearchTask(
                    run_id=run.id,
                    user_id=run.user_id,
                    task_type="research_professor",
                    target_id=program.id,
                    target_name=school.name,
                )
            )
        if program not in programs_added:
            programs_added.append(program)
    if seeds:
        await note_work_enqueued(session, run.id)
    link = await school_links.run_link(session, run.id, school.id)
    await session.commit()
    counts = await professor_counts(session, run.user_id, [p.id for p in programs_added])
    return {
        "id": school.id,
        "name": school.name,
        "country": school.country,
        "website_url": school.website_url,
        "image_url": school.image_url,
        "tier": link.tier if link is not None else None,
        "programs": [
            {
                "id": program.id,
                "name": program.name,
                "department_url": program.department_url,
                "professors": counts.get(program.id, 0),
            }
            for program in programs_added
        ],
    }


async def get_school(session: AsyncSession, user_id: str, school_id: str) -> dict:
    school = await get_school_or_404(session, school_id, user_id)
    programs = (
        (
            await session.execute(
                select(prospect_models.Program)
                .where(prospect_models.Program.school_id == school.id)
                .order_by(prospect_models.Program.name)
            )
        )
        .scalars()
        .all()
    )
    counts = await professor_counts(session, user_id, [p.id for p in programs])
    return {
        "id": school.id,
        "name": school.name,
        "country": school.country,
        "website_url": school.website_url,
        "image_url": school.image_url,
        "tier": school.tier,
        "programs": [
            {
                "id": p.id,
                "name": p.name,
                "department_url": p.department_url,
                "professors": counts.get(p.id, 0),
            }
            for p in programs
        ],
    }


SCHOOL_MUTABLE = {"name", "country", "website_url"}
PROGRAM_MUTABLE = {"name", "department_url"}
PROFESSOR_MUTABLE = {
    "name",
    "profile_url",
    "email",
    "openalex_id",
    "lab_name",
    "bio",
    "bio_source",
    "photo_url",
    "socials",
}


def _apply_allowlisted(row, data: dict, allowed: set[str]) -> None:
    for key, value in data.items():
        if key in allowed:
            setattr(row, key, value)


async def update_school(
    session: AsyncSession, user_id: str, school_id: str, data: dict
) -> dict:
    school = await get_school_or_404(session, school_id, user_id)
    _apply_allowlisted(school, data, SCHOOL_MUTABLE)
    await session.commit()
    return await get_school(session, user_id, school_id)


async def delete_school(session: AsyncSession, user_id: str, school_id: str) -> dict:
    """409 when any professor below has a candidate, so reviewed work is never
    orphaned. Pending tasks for removed programs are pruned; history is kept."""
    school = await get_school_or_404(session, school_id, user_id)
    program_ids = [
        row[0]
        for row in (
            await session.execute(
                select(prospect_models.Program.id).where(
                    prospect_models.Program.school_id == school.id
                )
            )
        ).all()
    ]
    professor_ids = []
    if program_ids:
        professor_ids = [
            row[0]
            for row in (
                await session.execute(
                    select(prospect_models.Professor.id).where(
                        prospect_models.Professor.program_id.in_(program_ids)
                    )
                )
            ).all()
        ]
    await guard_no_reviewed(session, "School", professor_ids)
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
            delete(run_models.ResearchTask).where(
                run_models.ResearchTask.target_id.in_(program_ids),
                run_models.ResearchTask.user_id == user_id,
                run_models.ResearchTask.status.in_(
                    [run_models.TaskStatus.pending, run_models.TaskStatus.deferred]
                ),
            )
        )
        await session.execute(
            delete(prospect_models.Program).where(
                prospect_models.Program.id.in_(program_ids)
            )
        )
    await session.execute(
        delete(prospect_models.School).where(prospect_models.School.id == school.id)
    )
    await session.commit()
    return {"status": "deleted"}


async def create_program(
    session: AsyncSession,
    user_id: str,
    school_id: str,
    *,
    name: str,
    department_url: str | None,
) -> dict:
    """Queued for faculty research like an agent-saved one."""
    school = await get_school_or_404(session, school_id, user_id)
    run_id = await _school_run_id(session, school)
    program = await _account_program(
        session, school, name=name, department_url=department_url
    )
    if not await school_links.program_in_run(session, run_id, program.id):
        session.add(
            run_models.ResearchTask(
                run_id=run_id,
                user_id=school.user_id,
                task_type="research_professor",
                target_id=program.id,
                target_name=school.name,
            )
        )
        await note_work_enqueued(session, run_id)
    await session.commit()
    return {
        "id": program.id,
        "name": program.name,
        "department_url": program.department_url,
        "school_id": school.id,
        "school_name": school.name,
        "run_id": run_id,
        "professors": [],
    }


async def get_program(session: AsyncSession, user_id: str, program_id: str) -> dict:
    program = await get_program_or_404(session, program_id, user_id)
    school = await get_school_or_404(session, program.school_id, user_id)
    professors = (
        (
            await session.execute(
                select(prospect_models.Professor)
                .where(prospect_models.Professor.program_id == program.id)
                .order_by(prospect_models.Professor.name)
            )
        )
        .scalars()
        .all()
    )
    counts = await paper_counts(session, user_id, [p.id for p in professors])
    return {
        "id": program.id,
        "name": program.name,
        "department_url": program.department_url,
        "school_id": school.id,
        "school_name": school.name,
        "professors": [
            {
                "id": p.id,
                "name": p.name,
                "openalex_id": p.openalex_id,
                "profile_url": p.profile_url,
                "lab_name": p.lab_name,
                "photo_url": p.photo_url,
                "papers": counts.get(p.id, 0),
            }
            for p in professors
        ],
    }


async def update_program(
    session: AsyncSession, user_id: str, program_id: str, data: dict
) -> dict:
    program = await get_program_or_404(session, program_id, user_id)
    _apply_allowlisted(program, data, PROGRAM_MUTABLE)
    await session.commit()
    out = await get_program(session, user_id, program_id)
    out["run_id"] = await school_links.latest_run_id(session, program.school_id)
    return out


async def run_faculty(session: AsyncSession, user_id: str, run_id: str) -> list[dict]:
    """One row per professor with names, paper count and this run's candidate."""
    await get_run_or_404(session, run_id, user_id)
    rows = (
        await session.execute(
            select(
                prospect_models.Professor,
                prospect_models.Program.id,
                prospect_models.Program.name,
                prospect_models.School.id,
                prospect_models.School.name,
            )
            .join(
                prospect_models.Program,
                prospect_models.Program.id == prospect_models.Professor.program_id,
            )
            .join(
                prospect_models.School,
                prospect_models.School.id == prospect_models.Program.school_id,
            )
            .where(
                prospect_models.School.id.in_(school_links.run_school_ids(run_id)),
                prospect_models.Professor.user_id == user_id,
            )
            .order_by(
                prospect_models.School.name,
                prospect_models.Program.name,
                prospect_models.Professor.name,
            )
        )
    ).all()
    professors = [row[0] for row in rows]
    counts = await paper_counts(session, user_id, [p.id for p in professors])
    candidate_rows = (
        await session.execute(
            select(
                candidate_models.CandidateScore.professor_id,
                candidate_models.CandidateScore.id,
            ).where(
                candidate_models.CandidateScore.run_id == run_id,
                candidate_models.CandidateScore.user_id == user_id,
            )
        )
    ).all()
    candidate_by_professor = {
        professor_id: candidate_id for professor_id, candidate_id in candidate_rows
    }
    return [
        {
            "id": professor.id,
            "name": professor.name,
            "program_id": program_id,
            "program": program_name,
            "school_id": school_id,
            "school": school_name,
            "lab_name": professor.lab_name,
            "photo_url": professor.photo_url,
            "papers": counts.get(professor.id, 0),
            "candidate_id": candidate_by_professor.get(professor.id),
        }
        for professor, program_id, program_name, school_id, school_name in rows
    ]


async def list_account_schools(
    session: AsyncSession, user_id: str, tier: str | None = None
) -> list[dict]:
    """With `tier`, only schools in that tier ("none": in no tier)."""
    query = select(prospect_models.School).where(prospect_models.School.user_id == user_id)
    if tier == "none":
        query = query.where(prospect_models.School.tier.is_(None))
    elif tier:
        query = query.where(prospect_models.School.tier == tier)
    schools = (
        (await session.execute(query.order_by(prospect_models.School.name)))
        .scalars()
        .all()
    )
    school_ids = [s.id for s in schools]
    if not school_ids:
        return []
    programs = (
        (
            await session.execute(
                select(prospect_models.Program)
                .where(prospect_models.Program.school_id.in_(school_ids))
                .order_by(prospect_models.Program.name)
            )
        )
        .scalars()
        .all()
    )
    counts = await professor_counts(session, user_id, [p.id for p in programs])
    by_school: dict[str, list] = {}
    for p in programs:
        by_school.setdefault(p.school_id, []).append(p)
    links = (
        await session.execute(
            select(prospect_models.RunSchool.school_id, prospect_models.RunSchool.run_id)
            .where(prospect_models.RunSchool.school_id.in_(school_ids))
            .order_by(prospect_models.RunSchool.found_at)
        )
    ).all()
    runs_by_school: dict[str, list[str]] = {}
    for school_id, run_id in links:
        runs_by_school.setdefault(school_id, []).append(run_id)
    return [
        {
            "id": school.id,
            "name": school.name,
            "country": school.country,
            "website_url": school.website_url,
            "image_url": school.image_url,
            "tier": school.tier,
            "run_ids": runs_by_school.get(school.id, []),
            "programs": [
                {
                    "id": p.id,
                    "name": p.name,
                    "department_url": p.department_url,
                    "professors": counts.get(p.id, 0),
                }
                for p in by_school.get(school.id, [])
            ],
        }
        for school in schools
    ]


async def school_faculty(session: AsyncSession, user_id: str, school_id: str) -> list[dict]:
    """One row per professor, with their best candidate from any run."""
    school = await get_school_or_404(session, school_id, user_id)
    return await _faculty_rows(session, user_id, school.id)


async def list_professors(session: AsyncSession, user_id: str) -> list[dict]:
    """Saved professors once per person (best-scored row), then ones only looked up."""
    rows: dict[str, dict] = {}
    seen: set[tuple[str, str]] = set()
    for row in await _faculty_rows(session, user_id):
        key = row.pop("person") or row["id"]
        held = rows.get(key)
        if held is None or (row["similarity_score"] or -1) > (held["similarity_score"] or -1):
            rows[key] = row
        seen.add((name_key(row["name"]), row["school_id"]))
    Entry = prospect_models.ProfessorIndex
    entries = (
        await session.execute(
            select(Entry).where(Entry.user_id == user_id, Entry.outcome == "no_match").order_by(Entry.name)
        )
    ).scalars().all()
    for e in entries:
        if (e.index_professor_id and e.index_professor_id in rows) or (e.name_key, e.school_id or "") in seen:
            continue
        rows[e.id] = {
            "id": e.id, "name": e.name, "program_id": e.program_id or "", "program": e.program_name or "",
            "school_id": e.school_id or "", "school": e.school_name, "lab_name": None, "photo_url": None,
            "papers": len(e.works or []), "candidate_id": None,
        }
    return sorted(rows.values(), key=lambda r: r["name"].lower())


async def _faculty_rows(session: AsyncSession, user_id: str, school_id: str | None = None) -> list[dict]:
    Professor, Program, School = prospect_models.Professor, prospect_models.Program, prospect_models.School
    query = (
        select(Professor, Program.id, Program.name, School.id, School.name, School.image_url)
        .join(Program, Program.id == Professor.program_id)
        .join(School, School.id == Program.school_id)
        .where(Professor.user_id == user_id)
        .order_by(Program.name, Professor.name)
    )
    if school_id is not None:
        query = query.where(School.id == school_id)
    rows = (await session.execute(query)).all()
    professors = [row[0] for row in rows]
    counts = await paper_counts(session, user_id, [p.id for p in professors])
    best: dict[str, candidate_models.CandidateScore] = {}
    if professors:
        candidates = (
            (
                await session.execute(
                    select(candidate_models.CandidateScore).where(
                        candidate_models.CandidateScore.professor_id.in_([p.id for p in professors]),
                        candidate_models.CandidateScore.user_id == user_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        for c in candidates:
            held = best.get(c.professor_id)
            if held is None or (c.similarity_score or -1) > (held.similarity_score or -1):
                best[c.professor_id] = c
    out = []
    for professor, program_id, program_name, sid, school_name, school_image in rows:
        c = best.get(professor.id)
        out.append(
            {
                "id": professor.id,
                "name": professor.name,
                "program_id": program_id,
                "program": program_name,
                "school_id": sid,
                "school": school_name,
                "lab_name": professor.lab_name,
                "photo_url": professor.photo_url,
                "bio": professor.bio,
                "school_image_url": school_image,
                "papers": counts.get(professor.id, 0),
                "candidate_id": c.id if c else None,
                "candidate_status": c.status if c else None,
                "similarity_score": c.similarity_score if c else None,
                "candidate_run_id": c.run_id if c else None,
                "person": professor.index_professor_id,
            }
        )
    return out


MATCH_TOP_PAPERS = 3
MATCH_INTEREST_CHARS = 600


async def match_professor(
    session: AsyncSession,
    user_id: str,
    professor_id: str,
    *,
    run_id: str | None = None,
    document_id: str | None = None,
    save: bool,
) -> dict:
    """With `save`, keep a candidate in the run (for a document, its newest run).
    A professor only looked up is saved to its programme first."""
    from api.cv import models as cv_models

    if run_id:
        run = await get_run_or_404(session, run_id, user_id)
        interest = run.interest_statement
    elif document_id:
        Doc = cv_models.CvDocument
        doc = (
            await session.execute(select(Doc).where(Doc.id == document_id, Doc.user_id == user_id, Doc.kind == "interest"))
        ).scalar_one_or_none()
        if doc is None:
            raise NotFoundError("Interest document not found")
        interest = doc.markdown
        run = (
            await session.execute(
                select(run_models.Run)
                .where(run_models.Run.user_id == user_id, run_models.Run.interest_document_id == doc.id)
                .order_by(run_models.Run.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    else:
        raise BadRequestError("Pick a run or an interest document.")
    if not interest.strip():
        raise BadRequestError("These interests are empty.")
    try:
        professor = await get_professor_or_404(session, professor_id, user_id)
        entry = None
        papers = [
            {"id": p.id, "title": p.title, "abstract": p.abstract, "year": p.year, "url": p.url}
            for p in (
                await session.execute(select(prospect_models.Paper).where(prospect_models.Paper.professor_id == professor.id))
            ).scalars()
        ]
    except NotFoundError:
        professor = None
        entry = await _indexed_or_404(session, user_id, professor_id)
        papers = [
            {"title": w.get("title") or "Untitled", "abstract": w.get("abstract"), "year": w.get("year"), "url": w.get("url")}
            for w in entry.works or []
        ]
    texts = [p["abstract"] or p["title"] for p in papers]
    if not any(texts):
        raise BadRequestError("This professor has no papers to score.")
    scored = await asyncio.to_thread(scoring.embed_and_score, interest, texts)
    band = scoring.score_band(scored["score"], scored.get("method"))
    best = papers[scored["best_index"]]["title"] if scored["best_index"] is not None else None
    ranked = sorted(zip(scored.get("all_scores") or [], papers), key=lambda pair: -pair[0])
    result = {
        "score": scored["score"], "band": band, "paper": best, "candidate_id": None,
        "run_id": run.id if run else None,
        "top_papers": [
            {"title": p["title"], "year": p["year"], "abstract": p["abstract"], "url": p["url"], "score": round(float(score), 4)}
            for score, p in ranked[:MATCH_TOP_PAPERS]
        ],
        "interest": interest[:MATCH_INTEREST_CHARS],
        "papers_scored": len([t for t in texts if t]),
        "fit": await verification.rate_fit(interest, [p for _, p in ranked], user_id),
    }
    if not save:
        return result
    if run is None:
        raise BadRequestError("No run uses this interest document yet, so there's no list of matches to save to.")

    if professor is None:
        professor = await _save_indexed(session, user_id, entry)
    candidate = (
        await session.execute(
            select(candidate_models.CandidateScore).where(
                candidate_models.CandidateScore.run_id == run.id,
                candidate_models.CandidateScore.professor_id == professor.id,
            )
        )
    ).scalars().first()
    if candidate is None:
        candidate = candidate_models.CandidateScore(
            run_id=run.id, user_id=user_id, professor_id=professor.id,
            status=candidate_models.CandidateStatus.scored,
        )
        session.add(candidate)
    candidate.similarity_score = scored["score"]
    # A research agent's rationale says more than this line, so a re-score keeps it.
    if not candidate.rationale or candidate.rationale.startswith("Checked by hand"):
        candidate.rationale = f"Checked by hand: a {band} fit" + (f", closest paper \"{best}\"." if best else ".")
    await session.flush()
    async with index_sync.guarded(session, f"candidate {candidate.id}"):
        await index_sync.sync_candidate_id(session, candidate.id)
    await session.commit()
    return {**result, "candidate_id": candidate.id}


async def delete_program(session: AsyncSession, user_id: str, program_id: str) -> dict:
    """Same 409 rule and task pruning as delete_school."""
    program = await get_program_or_404(session, program_id, user_id)
    professor_ids = [
        row[0]
        for row in (
            await session.execute(
                select(prospect_models.Professor.id).where(
                    prospect_models.Professor.program_id == program.id
                )
            )
        ).all()
    ]
    await guard_no_reviewed(session, "Program", professor_ids)
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
    await session.execute(
        delete(run_models.ResearchTask).where(
            run_models.ResearchTask.target_id == program.id,
            run_models.ResearchTask.user_id == user_id,
            run_models.ResearchTask.status.in_(
                [run_models.TaskStatus.pending, run_models.TaskStatus.deferred]
            ),
        )
    )
    await session.execute(
        delete(prospect_models.Program).where(prospect_models.Program.id == program.id)
    )
    await session.commit()
    return {"status": "deleted"}


async def get_professor(session: AsyncSession, user_id: str, professor_id: str) -> dict:
    try:
        professor = await get_professor_or_404(session, professor_id, user_id)
    except NotFoundError:
        entry = (await session.execute(select(prospect_models.ProfessorIndex).where(
            prospect_models.ProfessorIndex.id == professor_id,
            prospect_models.ProfessorIndex.user_id == user_id,
        ))).scalar_one_or_none()
        if entry is None:
            raise NotFoundError("Professor not found") from None
        return {
            "id": entry.id, "name": entry.name, "school_name": entry.school_name,
            "program_id": entry.program_id or "", "program_name": entry.program_name or "",
            "profile_url": entry.profile_url, "openalex_id": entry.openalex_id,
            "papers": [{"title": w.get("title", "Untitled"), "abstract": w.get("abstract"),
                        "year": w.get("year"), "url": w.get("url"), "citations": w.get("citations"),
                        "publication_type": w.get("publication_type"), "coauthors": w.get("coauthors") or []} for w in (entry.works or [])],
        }
    program = await get_program_or_404(session, professor.program_id, user_id)
    school = await get_school_or_404(session, program.school_id, user_id)
    papers = (
        (
            await session.execute(
                select(prospect_models.Paper).where(
                    prospect_models.Paper.professor_id == professor.id
                )
            )
        )
        .scalars()
        .all()
    )
    # Shared programmes can have a candidate per run: link the latest.
    candidate_id = (
        await session.execute(
            select(candidate_models.CandidateScore.id)
            .where(
                candidate_models.CandidateScore.professor_id == professor.id,
                candidate_models.CandidateScore.user_id == user_id,
            )
            .order_by(
                candidate_models.CandidateScore.created_at.desc(),
                candidate_models.CandidateScore.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return {
        "id": professor.id,
        "name": professor.name,
        "profile_url": professor.profile_url,
        "email": professor.email,
        "openalex_id": professor.openalex_id,
        "lab_name": professor.lab_name,
        "bio": professor.bio,
        "bio_source": professor.bio_source,
        "photo_url": professor.photo_url,
        "socials": professor.socials or [],
        "program_id": program.id,
        "program_name": program.name,
        "school_name": school.name,
        "candidate_id": candidate_id,
        "papers": [
            {"id": p.id, "title": p.title, "abstract": p.abstract, "year": p.year, "url": p.url,
             "citations": p.citations, "publication_type": p.publication_type, "coauthors": p.coauthors or []}
            for p in papers
        ],
    }


async def update_professor(
    session: AsyncSession, user_id: str, professor_id: str, data: dict
) -> dict:
    """A professor only looked up is saved to its programme first."""
    try:
        professor = await get_professor_or_404(session, professor_id, user_id)
    except NotFoundError:
        entry = await _indexed_or_404(session, user_id, professor_id)
        professor = await _save_indexed(session, user_id, entry)
    _apply_allowlisted(professor, data, PROFESSOR_MUTABLE)
    await session.commit()
    return await get_professor(session, user_id, professor.id)


async def save_professor_papers(
    session: AsyncSession, user_id: str, professor_id: str, openalex_id: str
) -> dict:
    """Works come from OpenAlex, never the caller, so nothing is made up."""
    from api.prospects import openalex

    try:
        professor = await get_professor_or_404(session, professor_id, user_id)
    except NotFoundError:
        professor = await _save_indexed(session, user_id, await _indexed_or_404(session, user_id, professor_id))
    author = canonical_openalex_id(openalex_id)
    if not re.fullmatch(r"A\d+", author):
        raise BadRequestError("That isn't an OpenAlex author id (A followed by digits).")
    works = await openalex.get_recent_works(author)
    if not works:
        raise BadRequestError("OpenAlex has no recent works for that author.")
    have = {
        normalize_text(p.title): p
        for p in (
            await session.execute(select(prospect_models.Paper).where(prospect_models.Paper.professor_id == professor.id))
        ).scalars()
    }
    added = 0
    for w in works:
        if not w.get("title"):
            continue
        known = have.get(normalize_text(w["title"]))
        if known is not None:
            # A paper saved before: refresh what OpenAlex now says about it.
            known.citations = w.get("citations", known.citations)
            known.publication_type = w.get("publication_type") or known.publication_type
            known.coauthors = w.get("coauthors") or known.coauthors
            continue
        paper = prospect_models.Paper(
            professor_id=professor.id, user_id=user_id, title=w["title"],
            abstract=w.get("abstract"), year=w.get("year"), url=w.get("url"),
            citations=w.get("citations"), publication_type=w.get("publication_type"), coauthors=w.get("coauthors"),
        )
        have[normalize_text(w["title"])] = paper
        session.add(paper)
        added += 1
    professor.openalex_id = professor.openalex_id or author
    await session.flush()
    async with index_sync.guarded(session, f"professor {professor.id}"):
        await index_sync.sync_professor(session, professor)
    await session.commit()
    return {**await get_professor(session, user_id, professor.id), "papers_added": added}


async def _indexed_or_404(session: AsyncSession, user_id: str, entry_id: str) -> prospect_models.ProfessorIndex:
    entry = (
        await session.execute(
            select(prospect_models.ProfessorIndex).where(
                prospect_models.ProfessorIndex.id == entry_id,
                prospect_models.ProfessorIndex.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        raise NotFoundError("Professor not found")
    return entry


async def _save_indexed(
    session: AsyncSession, user_id: str, entry: prospect_models.ProfessorIndex
) -> prospect_models.Professor:
    """Save a looked-up professor to its programme, with fetched works as papers."""
    if not entry.program_id:
        raise BadRequestError("The programme this professor was found in has been deleted.")
    program = await get_program_or_404(session, entry.program_id, user_id)
    professor = prospect_models.Professor(
        program_id=program.id, user_id=user_id, name=entry.name,
        profile_url=entry.profile_url, openalex_id=entry.openalex_id,
    )
    session.add(professor)
    await session.flush()
    for w in entry.works or []:
        session.add(prospect_models.Paper(
            professor_id=professor.id, user_id=user_id, title=w.get("title") or "Untitled",
            abstract=w.get("abstract"), year=w.get("year"), url=w.get("url"),
            citations=w.get("citations"), publication_type=w.get("publication_type"), coauthors=w.get("coauthors"),
        ))
    await session.flush()
    async with index_sync.guarded(session, f"professor {professor.id}"):
        await index_sync.sync_professor(session, professor)
    return professor


async def delete_professor(session: AsyncSession, user_id: str, professor_id: str) -> dict:
    """409 when a candidate exists."""
    professor = await get_professor_or_404(session, professor_id, user_id)
    await guard_no_reviewed(session, "Professor", [professor.id])
    await session.execute(
        delete(prospect_models.Paper).where(
            prospect_models.Paper.professor_id == professor.id
        )
    )
    await session.execute(
        delete(prospect_models.Professor).where(
            prospect_models.Professor.id == professor.id
        )
    )
    await session.commit()
    return {"status": "deleted"}


async def create_professor(
    session: AsyncSession,
    user_id: str,
    program_id: str,
    *,
    name: str,
    profile_url: str | None,
    email: str | None,
    openalex_id: str | None,
) -> dict:
    """Queued for narrow research like a spawned name."""
    program = await get_program_or_404(session, program_id, user_id)
    school = await get_school_or_404(session, program.school_id, user_id)
    run_id = await _school_run_id(session, school)
    # Hand-added professors skip the run's cap, so they need their own bound.
    waiting = (
        await session.execute(
            select(func.count())
            .select_from(prospect_models.Professor)
            .join(prospect_models.Program, prospect_models.Program.id == prospect_models.Professor.program_id)
            .join(prospect_models.School, prospect_models.School.id == prospect_models.Program.school_id)
            .where(
                prospect_models.School.id.in_(school_links.run_school_ids(run_id)),
                prospect_models.Professor.user_id == user_id,
                ~select(candidate_models.CandidateScore.id)
                .where(candidate_models.CandidateScore.professor_id == prospect_models.Professor.id)
                .exists(),
            )
        )
    ).scalar() or 0
    if waiting >= settings.max_user_professors_per_run:
        raise BadRequestError(
            f"{waiting} professors you added to this run are still waiting to be "
            "researched. Add more once some are done."
        )
    professor = prospect_models.Professor(
        program_id=program.id,
        user_id=program.user_id,
        name=name,
        profile_url=profile_url,
        email=email,
        openalex_id=openalex_id,
    )
    session.add(professor)
    await session.flush()
    async with index_sync.guarded(session, f"professor {professor.id}"):
        await index_sync.sync_professor(session, professor)
    session.add(
        run_models.ResearchTask(
            run_id=run_id,
            user_id=school.user_id,
            task_type="research_one_professor",
            target_id=program.id,
            target_name=name,
        )
    )
    await note_work_enqueued(session, run_id)
    await session.commit()
    return await get_professor(session, user_id, professor.id)
