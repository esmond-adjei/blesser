"""Per-account professor index (never shared between accounts).

Every finished lookup is kept, match or not: the OpenAlex author, the
works fetched, the conclusion. Later tasks reuse it by name at the same
school before any OpenAlex call, or by author id once a search found them.
Entries older than PROFESSOR_INDEX_DAYS are ignored. Only what a task
already fetched is kept; opted-out people are never kept or reused.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from api.core.config import settings
from api.core.ids import new_id
from api.core.textnorm import canonical_openalex_id, normalize_text
from api.core.time import utcnow_naive
from api.index.keys import person_key as name_key
from api.prospects import grounding, institutions, optouts
from api.prospects import models as prospect_models

log = logging.getLogger(__name__)

Entry = prospect_models.ProfessorIndex


def school_key(name: str | None) -> str:
    return normalize_text(name)


def enabled() -> bool:
    return settings.professor_index_days > 0


def _cutoff() -> datetime:
    return utcnow_naive() - timedelta(days=settings.professor_index_days)


async def _usable(session, row: Entry | None) -> Entry | None:
    if row is None or not row.works:
        return None
    if await optouts.is_opted_out(
        session,
        openalex_id=(row.author or {}).get("openalex_id") or row.openalex_id,
        name=row.name,
        school=row.school_name,
    ):
        return None
    return row


async def lookup(session, user_id: str, school, name: str) -> Entry | None:
    """The account's fresh entry for this name at this school, or None."""
    key = name_key(name)
    if not enabled() or school is None or not key:
        return None
    row = (
        await session.execute(
            select(Entry)
            .where(
                Entry.user_id == user_id,
                Entry.name_key == key,
                or_(Entry.school_id == school.id, Entry.school_key == school_key(school.name)),
                Entry.looked_up_at >= _cutoff(),
            )
            .order_by(Entry.looked_up_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return await _usable(session, row)


async def lookup_author(session, user_id: str, openalex_id: str) -> Entry | None:
    """The account's freshest entry for this OpenAlex author, or None."""
    if not enabled() or not openalex_id:
        return None
    row = (
        await session.execute(
            select(Entry)
            .where(
                Entry.user_id == user_id,
                Entry.openalex_id == canonical_openalex_id(openalex_id),
                Entry.looked_up_at >= _cutoff(),
            )
            .order_by(Entry.looked_up_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return await _usable(session, row)


def _reused(ctx) -> set[str]:
    value = getattr(ctx, "indexed_authors", None)
    if value is None:
        value = set()
        ctx.indexed_authors = value
    return value


def use(ctx, entry: Entry) -> dict:
    """Record an entry on the task as if just looked up, for scoring and grounding."""
    author = {**(entry.author or {})}
    author["openalex_id"] = author.get("openalex_id") or entry.openalex_id
    grounding.record_author_candidates(ctx, [author])
    grounding.record_works(ctx, author["openalex_id"], entry.works or [])
    _reused(ctx).add(canonical_openalex_id(author["openalex_id"]))
    return author


def _looked_up(ctx, school) -> tuple[dict, list[dict]] | None:
    """The single author this task found and fetched works for, with them; else None."""
    candidates = getattr(ctx, "author_candidates", None) or {}
    works_by_author = getattr(ctx, "works_by_author", None) or {}
    school_id, school_names = institutions.stored(school)
    found = [
        (candidates[author_id], works)
        for author_id, works in works_by_author.items()
        if works
        and author_id in candidates
        and grounding._institution_matches(
            candidates[author_id], school.name, school_id, school_names
        )
    ]
    return found[0] if len(found) == 1 else None


async def _profile_url(session, candidate_id: str | None) -> str | None:
    if candidate_id is None:
        return None
    from api.candidates import models as candidate_models

    return (
        await session.execute(
            select(prospect_models.Professor.profile_url)
            .join(
                candidate_models.CandidateScore,
                candidate_models.CandidateScore.professor_id == prospect_models.Professor.id,
            )
            .where(candidate_models.CandidateScore.id == candidate_id)
        )
    ).scalar_one_or_none()


async def remember(ctx, school, name: str) -> bool:
    """Keep what this task looked up. A reused entry is left as is, so its age
    counts from the original lookup. Returns whether one was written; never raises."""
    program = getattr(ctx, "program", None)
    if not enabled() or school is None or program is None:
        return False
    found = _looked_up(ctx, school)
    if found is None:
        return False
    author, works = found
    author_id = canonical_openalex_id(str(author.get("openalex_id") or ""))
    if not author_id or author_id in _reused(ctx):
        return False
    session = ctx.session
    if await optouts.is_opted_out(
        session, openalex_id=author.get("openalex_id"), name=name, school=school.name
    ):
        return False
    candidate_id = getattr(ctx, "last_candidate_id", None)
    scores = getattr(ctx, "alignment_scores", None) or []
    values = {
        "user_id": ctx.user_id,
        "name": name,
        "name_key": name_key(name),
        "school_id": school.id,
        "school_name": school.name,
        "school_key": school_key(school.name),
        "program_id": program.id,
        "program_name": program.name,
        "openalex_id": author_id,
        "author": author,
        "works": works,
        "profile_url": await _profile_url(session, candidate_id),
        "outcome": "match" if candidate_id is not None else "no_match",
        "score": scores[-1]["score"] if scores else None,
        "run_id": ctx.run.id,
        "looked_up_at": utcnow_naive(),
    }
    if not values["name_key"] or not values["school_key"]:
        return False
    try:
        async with session.begin_nested():
            await session.execute(
                insert(Entry)
                .values(id=new_id(), **values)
                .on_conflict_do_update(constraint="uq_professor_index_school_name", set_=values)
            )
        await session.commit()
    except Exception as exc:  # noqa: BLE001 - an index, never a failed task
        log.info("professor index write skipped: %s", type(exc).__name__)
        return False
    return True


__all__ = ["enabled", "lookup", "lookup_author", "name_key", "remember", "use"]
