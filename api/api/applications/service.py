"""Application tracker storage: CRUD plus the agent upsert.

Humans own degree_type and status; agent saves only fill empty fields and merge
lists. school + program (normalized) is the upsert key.
"""

import re

from sqlalchemy import select

from api.applications import models as application_models
from api.applications import schemas as application_schemas
from api.applications.dates import parse_deadline
from api.candidates import models as candidate_models
from api.core.exceptions import NotFoundError
from api.prospects import models as prospect_models


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", (text or "").lower())).strip()


def to_out(app: application_models.Application) -> dict:
    return {
        "id": app.id,
        "school": app.school,
        "program": app.program,
        "degree_type": app.degree_type,
        "location": app.location,
        "link": app.link,
        "requirements": app.requirements or [],
        "offer": app.offer,
        "deadline": app.deadline,
        "deadline_date": app.deadline_date,
        "status": app.status,
        "professors": app.professors or [],
        "notes": app.notes,
        "fee_waiver": app.fee_waiver,
        "fee_waiver_notes": app.fee_waiver_notes,
        "source": app.source,
        "run_id": app.run_id,
        "opportunity_id": app.opportunity_id,
        "created_at": app.created_at,
        "updated_at": app.updated_at,
    }


async def list_applications(session, user_id: str) -> list[dict]:
    result = await session.execute(
        select(application_models.Application)
        .where(application_models.Application.user_id == user_id)
        .order_by(application_models.Application.created_at.asc())
    )
    images = await school_images(session, user_id)
    return [
        {**to_out(a), "school_image_url": images.get(_normalize(a.school))}
        for a in result.scalars().all()
    ]


async def school_images(session, user_id: str) -> dict[str, str]:
    """{normalized school name: image url}; applications store the school by name."""
    rows = await session.execute(
        select(prospect_models.School.name, prospect_models.School.image_url).where(
            prospect_models.School.user_id == user_id,
            prospect_models.School.image_url.is_not(None),
        )
    )
    return {_normalize(name): url for name, url in rows.all() if url}


async def get_application_or_404(session, application_id: str, user_id: str):
    app = (
        (
            await session.execute(
                select(application_models.Application).where(
                    application_models.Application.id == application_id,
                    application_models.Application.user_id == user_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if app is None:
        raise NotFoundError("Application not found")
    return app


async def create_application(
    session, user_id: str, data: application_schemas.ApplicationCreate
) -> dict:
    app = application_models.Application(
        user_id=user_id,
        school=data.school.strip(),
        program=data.program.strip(),
        degree_type=data.degree_type,
        location=data.location,
        link=data.link,
        requirements=[r.model_dump() for r in data.requirements],
        offer=data.offer,
        deadline=data.deadline,
        deadline_date=data.deadline_date or parse_deadline(data.deadline),
        status=data.status.value,
        professors=[p.model_dump() for p in data.professors],
        notes=data.notes,
        fee_waiver=data.fee_waiver,
        fee_waiver_notes=data.fee_waiver_notes,
        source=application_models.ApplicationSource.manual.value,
        run_id=None,
    )
    session.add(app)
    await session.commit()
    await session.refresh(app)
    return to_out(app)


async def update_application(
    session, user_id: str, application_id: str, data: application_schemas.ApplicationUpdate
) -> dict:
    app = await get_application_or_404(session, application_id, user_id)
    patch = data.model_dump(exclude_unset=True, mode="json")
    # Kept as a date, not the JSON-mode string.
    patch.pop("deadline_date", None)
    for field, value in patch.items():
        setattr(app, field, value)
    if "deadline_date" in data.model_fields_set:
        app.deadline_date = data.deadline_date
    elif "deadline" in patch:
        app.deadline_date = parse_deadline(app.deadline)
    await session.commit()
    await session.refresh(app)
    return to_out(app)


async def delete_application(session, user_id: str, application_id: str) -> dict:
    app = await get_application_or_404(session, application_id, user_id)
    await session.delete(app)
    await session.commit()
    return {"status": "deleted"}


async def find_match(
    session, user_id: str, school: str, program: str
) -> application_models.Application | None:
    key_school, key_program = _normalize(school), _normalize(program)
    result = await session.execute(
        select(application_models.Application).where(
            application_models.Application.user_id == user_id
        )
    )
    for app in result.scalars().all():
        if _normalize(app.school) == key_school and _normalize(app.program) == key_program:
            return app
    return None


def _merge_requirements(
    stored: list, incoming: list[str]
) -> tuple[list, bool]:
    """Add unseen labels as undone; never remove rows or flip done flags."""
    seen = {_normalize(r.get("label", "")) for r in stored if isinstance(r, dict)}
    merged = list(stored)
    changed = False
    for label in incoming:
        label = (label or "").strip()
        if label and _normalize(label) not in seen:
            seen.add(_normalize(label))
            merged.append({"label": label, "done": False})
            changed = True
    return merged, changed


def _merge_professors(stored: list, incoming: list[str]) -> tuple[list, bool]:
    """Add unseen names (bare links); existing linked rows are untouched."""
    seen = {_normalize(p.get("name", "")) for p in stored if isinstance(p, dict)}
    merged = list(stored)
    changed = False
    for name in incoming:
        name = (name or "").strip()
        if name and _normalize(name) not in seen:
            seen.add(_normalize(name))
            merged.append({"name": name})
            changed = True
    return merged, changed


async def upsert_for_agent(
    session,
    user_id: str,
    run_id: str,
    data: application_schemas.AgentApplicationIn,
    agent_rows_only: bool = False,
) -> tuple[dict, bool, list[str]]:
    """Agent write: create, or fill empty fields on the matching row. Returns (row,
    created, updated_fields). With `agent_rows_only`, a student-created match is
    left untouched."""
    school = data.school.strip()
    program = (data.program or "").strip()
    app = await find_match(session, user_id, school, program)
    if (
        app is not None
        and agent_rows_only
        and app.source != application_models.ApplicationSource.agent.value
    ):
        return to_out(app), False, []
    if app is None:
        requirements, _ = _merge_requirements([], data.requirements)
        professors, _ = _merge_professors([], data.professors)
        app = application_models.Application(
            user_id=user_id,
            school=school,
            program=program,
            degree_type=data.degree_type or "phd",
            location=data.location,
            link=data.link,
            requirements=requirements,
            offer=data.offer,
            deadline=data.deadline,
            deadline_date=parse_deadline(data.deadline),
            status=application_models.ApplicationStatus.wishlist.value,
            professors=professors,
            notes=data.notes,
            fee_waiver=data.fee_waiver,
            fee_waiver_notes=data.fee_waiver_notes,
            source=application_models.ApplicationSource.agent.value,
            run_id=run_id,
        )
        session.add(app)
        await session.commit()
        await session.refresh(app)
        return to_out(app), True, ["created"]

    updated: list[str] = []
    # Fill-empty-only: researcher content always wins.
    if not app.location and data.location:
        app.location = data.location
        updated.append("location")
    if not app.link and data.link:
        app.link = data.link
        updated.append("link")
    if not app.offer and data.offer:
        app.offer = data.offer
        updated.append("offer")
    if not app.deadline and data.deadline:
        app.deadline = data.deadline
        app.deadline_date = app.deadline_date or parse_deadline(data.deadline)
        updated.append("deadline")
    if not app.notes and data.notes:
        app.notes = data.notes
        updated.append("notes")
    if not app.fee_waiver and data.fee_waiver:
        app.fee_waiver = True
        updated.append("fee_waiver")
    if not app.fee_waiver_notes and data.fee_waiver_notes:
        app.fee_waiver_notes = data.fee_waiver_notes
        updated.append("fee_waiver_notes")
    merged_reqs, reqs_changed = _merge_requirements(app.requirements or [], data.requirements)
    if reqs_changed:
        app.requirements = merged_reqs
        updated.append("requirements")
    merged_profs, profs_changed = _merge_professors(app.professors or [], data.professors)
    if profs_changed:
        app.professors = merged_profs
        updated.append("professors")
    if app.source == application_models.ApplicationSource.manual.value:
        # Provenance only: ownership and workflow stay with the researcher.
        app.run_id = app.run_id or run_id
    await session.commit()
    await session.refresh(app)
    return to_out(app), False, updated


async def resolve_professors(session, user_id: str, application_id: str) -> dict:
    """Backfill professor_id/candidate_id on bare name links.

    Professors match by normalized name (narrowed to the link's school); ambiguous
    names stay unresolved. Candidates prefer the application's own run, else the
    highest score. Researcher-set ids are never overwritten.
    """
    app = await get_application_or_404(session, application_id, user_id)
    professors = (
        (
            await session.execute(
                select(prospect_models.Professor).where(
                    prospect_models.Professor.user_id == user_id
                )
            )
        )
        .scalars()
        .all()
    )
    programs = {
        p.id: p
        for p in (
            (
                await session.execute(
                    select(prospect_models.Program).where(
                        prospect_models.Program.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )
    }
    schools = {
        s.id: s.name
        for s in (
            (
                await session.execute(
                    select(prospect_models.School).where(
                        prospect_models.School.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )
    }

    def school_of(professor) -> str:
        program = programs.get(professor.program_id)
        if program is None:
            return ""
        return schools.get(program.school_id, "")

    by_name: dict[str, list] = {}
    for professor in professors:
        by_name.setdefault(_normalize(professor.name), []).append(professor)

    resolved = []
    changed = False
    for link in app.professors or []:
        if not isinstance(link, dict):
            resolved.append(link)
            continue
        updated = dict(link)
        name = (updated.get("name") or "").strip()
        professor_id = updated.get("professor_id")
        if name and not professor_id:
            matches = list(by_name.get(_normalize(name), []))
            if updated.get("school"):
                narrowed = [
                    p
                    for p in matches
                    if _normalize(school_of(p)) == _normalize(updated["school"])
                ]
                if narrowed:
                    matches = narrowed
            if len(matches) == 1:
                professor_id = matches[0].id
                updated["professor_id"] = professor_id
        if professor_id and not updated.get("candidate_id"):
            candidate_stmt = select(candidate_models.CandidateScore).where(
                candidate_models.CandidateScore.professor_id == professor_id,
                candidate_models.CandidateScore.user_id == user_id,
            )
            if app.run_id:
                candidate_stmt = candidate_stmt.order_by(
                    (candidate_models.CandidateScore.run_id == app.run_id).desc()
                )
            candidate_stmt = candidate_stmt.order_by(
                candidate_models.CandidateScore.similarity_score.desc().nulls_last(),
                candidate_models.CandidateScore.id.asc(),
            )
            candidate = (await session.execute(candidate_stmt)).scalars().first()
            updated["candidate_id"] = candidate.id if candidate else None
        if updated != link:
            changed = True
        resolved.append(updated)

    if changed:
        app.professors = resolved
        await session.commit()
        await session.refresh(app)
    return to_out(app)
