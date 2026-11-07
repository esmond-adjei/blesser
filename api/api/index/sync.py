"""Mirror legacy rows (professors, papers, candidate_scores) into the index
and workspace, idempotently, so retries and resumed tasks are safe.

A failed sync never fails the write it follows (`guarded`): the legacy row is
the source of truth and the next sync catches up.
"""

from __future__ import annotations

import contextlib
import logging

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from api.candidates import models as candidate_models
from api.core.ids import new_id
from api.core.time import utcnow_naive
from api.cv import models as cv_models
from api.index import keys
from api.index import models as index_models
from api.outreach import models as outreach_models
from api.prospects import models as prospect_models
from api.prospects import optouts
from api.runs import models as run_models
from api.workspace import models as workspace_models

log = logging.getLogger(__name__)

#: Candidate statuses as match statuses; every other status is shortlisted.
MATCH_STATUS = {"rejected": "passed", "sent": "contacted"}

#: Professor fields copied into the index person, filled when empty.
_PROFILE_FIELDS = {
    "profile_url": "homepage_url",
    "email": "email",
    "lab_name": "lab_name",
    "bio": "bio",
    "photo_url": "photo_url",
}


@contextlib.asynccontextmanager
async def guarded(session, what: str):
    """Run a sync in a savepoint; log and roll back just it on failure."""
    try:
        async with session.begin_nested():
            yield
    except Exception:  # the legacy write must still land
        log.exception("index sync failed: %s", what)


def match_status(candidate_status) -> str:
    value = getattr(candidate_status, "value", candidate_status)
    return MATCH_STATUS.get(str(value), "shortlisted")


async def _named_at(session, user_id: str, name_key: str, school_id: str):
    """A person of this name affiliated with this school, if any."""
    Person = index_models.IndexProfessor
    return (
        await session.execute(
            select(Person)
            .join(index_models.Affiliation, index_models.Affiliation.professor_id == Person.id)
            .where(
                Person.user_id == user_id,
                Person.name_key == name_key,
                index_models.Affiliation.school_id == school_id,
            )
            .order_by(Person.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()


async def _person_for(session, professor, school) -> index_models.IndexProfessor:
    """The professor's person: by OpenAlex id, else the same name at the
    same school (unless OpenAlex says that is someone else), else new."""
    Person = index_models.IndexProfessor
    user_id = professor.user_id
    name_key = keys.person_key(professor.name)
    openalex_id = keys.openalex_author(professor.openalex_id)
    if openalex_id:
        known = (
            await session.execute(
                select(Person).where(Person.user_id == user_id, Person.openalex_id == openalex_id)
            )
        ).scalar_one_or_none()
        if known is not None:
            return known
    named = await _named_at(session, user_id, name_key, school.id)
    if named is not None and (not openalex_id or named.openalex_id in (None, openalex_id)):
        if openalex_id and named.openalex_id is None:
            named.openalex_id = openalex_id
        return named
    if openalex_id:
        # Another worker may be saving the same person right now.
        await session.execute(
            insert(Person)
            .values(
                id=new_id(),
                user_id=user_id,
                name=professor.name,
                name_key=name_key,
                openalex_id=openalex_id,
                socials=[],
                provenance={},
            )
            .on_conflict_do_nothing(constraint="uq_index_professor_openalex")
        )
        return (
            await session.execute(
                select(Person).where(Person.user_id == user_id, Person.openalex_id == openalex_id)
            )
        ).scalar_one()
    person = Person(user_id=user_id, name=professor.name, name_key=name_key, socials=[], provenance={})
    session.add(person)
    await session.flush()
    return person


def _fill_profile(person, professor, now) -> None:
    provenance = dict(person.provenance or {})
    for legacy, field in _PROFILE_FIELDS.items():
        value = getattr(professor, legacy)
        if value and not getattr(person, field):
            setattr(person, field, value)
            source = (professor.bio_source if field == "bio" else None) or "research"
            provenance[field] = {"source": source, "fetched_at": now.isoformat()}
    known = {(s or {}).get("url") for s in person.socials or []}
    extra = [s for s in professor.socials or [] if (s or {}).get("url") not in known]
    if extra:
        person.socials = [*(person.socials or []), *extra]
    if provenance != (person.provenance or {}):
        person.provenance = provenance
        person.profile_fetched_at = now


async def _affiliate(session, person, school_id: str, program_id: str | None, now) -> None:
    await session.execute(
        insert(index_models.Affiliation)
        .values(
            id=new_id(),
            professor_id=person.id,
            school_id=school_id,
            program_id=program_id,
            source="roster",
            verified_at=now,
        )
        .on_conflict_do_update(constraint="uq_affiliation_place", set_={"verified_at": now})
    )


async def _papers(session, person, professor, now) -> list[str]:
    """Index every paper of the professor row; returns their index ids."""
    papers = (
        await session.execute(
            select(prospect_models.Paper).where(prospect_models.Paper.professor_id == professor.id)
        )
    ).scalars().all()
    ids = []
    Paper = index_models.IndexPaper
    for paper in papers:
        if paper.index_paper_id is None:
            work_key = keys.work_key(title=paper.title, year=paper.year, url=paper.url)
            await session.execute(
                insert(Paper)
                .values(
                    id=new_id(),
                    user_id=professor.user_id,
                    work_key=work_key,
                    title=paper.title,
                    abstract=paper.abstract,
                    year=paper.year,
                    publication_type=paper.publication_type,
                    url=paper.url,
                    doi=keys.doi_of(paper.url),
                    source="openalex",
                    fetched_at=now,
                )
                .on_conflict_do_nothing(constraint="uq_index_paper_work")
            )
            paper.index_paper_id = (
                await session.execute(
                    select(Paper.id).where(Paper.user_id == professor.user_id, Paper.work_key == work_key)
                )
            ).scalar_one()
        if paper.publication_type:
            await session.execute(
                update(Paper).where(Paper.id == paper.index_paper_id, Paper.publication_type.is_(None))
                .values(publication_type=paper.publication_type)
            )
        await session.execute(
            insert(index_models.PaperAuthor)
            .values(paper_id=paper.index_paper_id, professor_id=person.id)
            .on_conflict_do_nothing()
        )
        ids.append(paper.index_paper_id)
    if ids and person.works_fetched_at is None:
        person.works_fetched_at = now
    return ids


async def sync_professor(session, professor) -> index_models.IndexProfessor | None:
    """The professor's index person, created or filled in, with affiliation and
    papers. None for a person who opted out."""
    program = await session.get(prospect_models.Program, professor.program_id)
    school = await session.get(prospect_models.School, program.school_id) if program else None
    if school is None:
        return None
    if await optouts.is_opted_out(
        session, openalex_id=professor.openalex_id, name=professor.name, school=school.name
    ):
        return None
    now = utcnow_naive()
    person = (
        await session.get(index_models.IndexProfessor, professor.index_professor_id)
        if professor.index_professor_id
        else None
    ) or await _person_for(session, professor, school)
    _fill_profile(person, professor, now)
    await _affiliate(session, person, school.id, program.id, now)
    await _papers(session, person, professor, now)
    professor.index_professor_id = person.id
    await session.flush()
    return person


def _interest_title(run) -> str:
    topic = " · ".join(p for p in (run.field, run.region) if p)
    return (f"Interests: {topic}" if topic else "Research interests")[:200]


async def ensure_interest_document(session, run) -> str | None:
    """The account's interest statement with the run's text, or a new one."""
    if run.interest_document_id:
        return run.interest_document_id
    text = (run.interest_statement or "").strip()
    if not text:
        return None
    Doc = cv_models.CvDocument
    doc_id = (
        await session.execute(
            select(Doc.id)
            .where(Doc.user_id == run.user_id, Doc.kind == "interest", Doc.markdown == text)
            .order_by(Doc.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    if doc_id is None:
        doc = Doc(
            user_id=run.user_id,
            title=_interest_title(run),
            kind="interest",
            format="md",
            status="ready",
            markdown=text,
            revision=1,
        )
        session.add(doc)
        await session.flush()
        doc_id = doc.id
    run.interest_document_id = doc_id
    return doc_id


async def sync_candidate(session, candidate) -> workspace_models.Match | None:
    """The candidate's match (user × person × interest statement) with this scoring
    in its history; the newest scoring sets the score and status."""
    professor = await session.get(prospect_models.Professor, candidate.professor_id)
    run = await session.get(run_models.Run, candidate.run_id)
    if professor is None or run is None:
        return None
    person = await sync_professor(session, professor)
    doc_id = await ensure_interest_document(session, run)
    if person is None or doc_id is None:
        return None
    Match = workspace_models.Match
    await session.execute(
        insert(Match)
        .values(
            id=new_id(),
            user_id=candidate.user_id,
            professor_id=person.id,
            interest_document_id=doc_id,
            status="shortlisted",
            notes="",
        )
        .on_conflict_do_nothing(constraint="uq_match_interest")
    )
    match = (
        await session.execute(
            select(Match).where(
                Match.user_id == candidate.user_id,
                Match.professor_id == person.id,
                Match.interest_document_id == doc_id,
            )
        )
    ).scalar_one()
    Score = workspace_models.MatchScore
    scoring = (
        await session.execute(select(Score).where(Score.candidate_id == candidate.id))
    ).scalar_one_or_none()
    if scoring is None:
        revision = (
            await session.execute(select(cv_models.CvDocument.revision).where(cv_models.CvDocument.id == doc_id))
        ).scalar_one()
        scoring = Score(
            match_id=match.id,
            candidate_id=candidate.id,
            run_id=candidate.run_id,
            interest_revision=revision,
            scored_at=candidate.created_at or utcnow_naive(),
        )
        session.add(scoring)
    scoring.score = candidate.similarity_score
    scoring.rationale = candidate.rationale
    await session.flush()
    newest = (
        await session.execute(
            select(Score.id).where(Score.match_id == match.id).order_by(Score.scored_at.desc(), Score.id.desc()).limit(1)
        )
    ).scalar_one()
    if newest == scoring.id:
        match.score = candidate.similarity_score
        match.rationale = candidate.rationale
        match.status = match_status(candidate.status)
    # sync_professor indexed the row's papers: they are the evidence.
    paper_ids = (
        await session.execute(
            select(prospect_models.Paper.index_paper_id).where(
                prospect_models.Paper.professor_id == professor.id,
                prospect_models.Paper.index_paper_id.is_not(None),
            )
        )
    ).scalars().all()
    for paper_id in paper_ids:
        await session.execute(
            insert(workspace_models.MatchEvidence)
            .values(match_id=match.id, paper_id=paper_id)
            .on_conflict_do_nothing()
        )
    candidate.match_id = match.id
    draft = (
        await session.execute(
            select(outreach_models.EmailDraft).where(outreach_models.EmailDraft.candidate_id == candidate.id)
        )
    ).scalar_one_or_none()
    if draft is not None:
        draft.match_id = match.id
    await session.flush()
    return match


async def sync_candidate_id(session, candidate_id: str) -> None:
    candidate = await session.get(candidate_models.CandidateScore, candidate_id)
    if candidate is not None:
        async with guarded(session, f"candidate {candidate_id}"):
            await sync_candidate(session, candidate)
