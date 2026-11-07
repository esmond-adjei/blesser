"""Opt-outs for the people Graduator researches (docs/data-handling.md).

`remove_person` deletes what every account holds about them; saves or new
research tasks matching an opt-out are refused from then on.
"""

import re

from sqlalchemy import delete, func, or_, select

from api.candidates import models as candidate_models
from api.core.textnorm import canonical_openalex_id
from api.index import models as index_models
from api.outreach import models as outreach_models
from api.prospects import models as prospect_models


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())).strip()


def name_key(name: str | None, school: str | None) -> str | None:
    n, s = _norm(name), _norm(school)
    return f"{n}|{s}" if n and s else None


async def is_opted_out(
    session,
    *,
    openalex_id: str | None = None,
    name: str | None = None,
    school: str | None = None,
) -> bool:
    clauses = []
    if openalex_id:
        clauses.append(prospect_models.ProfessorOptOut.openalex_id == openalex_id)
    key = name_key(name, school)
    if key:
        clauses.append(prospect_models.ProfessorOptOut.name_key == key)
    if not clauses:
        return False
    found = await session.execute(
        select(func.count())
        .select_from(prospect_models.ProfessorOptOut)
        .where(or_(*clauses))
    )
    return bool(found.scalar())


async def remove_person(
    session,
    *,
    openalex_id: str | None = None,
    name: str | None = None,
    school: str | None = None,
    email: str | None = None,
    note: str | None = None,
) -> dict:
    """Record the opt-out and delete matching records in every account,
    with their papers, candidates, drafts and index entries. Returns counts."""
    key = name_key(name, school)
    if not (openalex_id or key or email):
        raise ValueError("Give an OpenAlex id, an email, or a name with its school.")
    session.add(
        prospect_models.ProfessorOptOut(
            openalex_id=openalex_id or None,
            name_key=key,
            email=(email or "").strip().lower() or None,
            note=note,
        )
    )
    Professor = prospect_models.Professor
    rows = (
        await session.execute(
            select(Professor, prospect_models.School.name)
            .join(
                prospect_models.Program,
                Professor.program_id == prospect_models.Program.id,
            )
            .join(
                prospect_models.School,
                prospect_models.Program.school_id == prospect_models.School.id,
            )
        )
    ).all()
    matched = [
        prof.id
        for prof, school_name in rows
        if (openalex_id and prof.openalex_id == openalex_id)
        or (email and (prof.email or "").strip().lower() == email.strip().lower())
        or (key and name_key(prof.name, school_name) == key)
    ]
    counts = {
        "professors": len(matched),
        "candidates": 0,
        "drafts": 0,
        "papers": 0,
        "indexed": 0,
    }
    Entry = prospect_models.ProfessorIndex
    wanted_id = canonical_openalex_id(openalex_id) if openalex_id else None
    entries = (
        await session.execute(select(Entry.id, Entry.openalex_id, Entry.name, Entry.school_name))
    ).all()
    indexed = [
        row.id
        for row in entries
        if (wanted_id and row.openalex_id == wanted_id)
        or (key and name_key(row.name, row.school_name) == key)
    ]
    if indexed:
        await session.execute(delete(Entry).where(Entry.id.in_(indexed)))
        counts["indexed"] = len(indexed)
    # Their index person goes too, with affiliations, authorships and matches.
    Person = index_models.IndexProfessor
    people = (
        await session.execute(
            select(Person.id, Person.openalex_id, Person.name, Person.email, prospect_models.School.name)
            .outerjoin(index_models.Affiliation, index_models.Affiliation.professor_id == Person.id)
            .outerjoin(prospect_models.School, prospect_models.School.id == index_models.Affiliation.school_id)
        )
    ).all()
    gone = {
        row[0]
        for row in people
        if (wanted_id and row[1] == wanted_id)
        or (email and (row[3] or "").strip().lower() == email.strip().lower())
        or (key and name_key(row[2], row[4]) == key)
    }
    if gone:
        await session.execute(delete(Person).where(Person.id.in_(gone)))
    counts["index_professors"] = len(gone)
    if matched:
        candidate_ids = (
            (
                await session.execute(
                    select(candidate_models.CandidateScore.id).where(
                        candidate_models.CandidateScore.professor_id.in_(matched)
                    )
                )
            )
            .scalars()
            .all()
        )
        if candidate_ids:
            drafts = await session.execute(
                delete(outreach_models.EmailDraft).where(
                    outreach_models.EmailDraft.candidate_id.in_(candidate_ids)
                )
            )
            counts["drafts"] = drafts.rowcount or 0
            cands = await session.execute(
                delete(candidate_models.CandidateScore).where(
                    candidate_models.CandidateScore.id.in_(candidate_ids)
                )
            )
            counts["candidates"] = cands.rowcount or 0
        papers = await session.execute(
            delete(prospect_models.Paper).where(
                prospect_models.Paper.professor_id.in_(matched)
            )
        )
        counts["papers"] = papers.rowcount or 0
        await session.execute(delete(Professor).where(Professor.id.in_(matched)))
    await session.commit()
    return counts
