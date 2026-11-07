"""School → OpenAlex institution, resolved once per school and stored.

Grounding compares institution ids, with names as the fallback: name
tokens alone mismatch acronyms, accents and affiliated hospitals.
"""

from __future__ import annotations

import json
import logging

import httpx

from api.core.config import settings
from api.prospects import openalex

log = logging.getLogger(__name__)


def stored(school) -> tuple[str | None, list[str]]:
    try:
        names = json.loads(school.institution_names or "[]")
    except (TypeError, ValueError):
        names = []
    return school.openalex_institution_id, [n for n in names if isinstance(n, str)]


async def resolve_school(session, school) -> tuple[str | None, list[str]]:
    """A lookup that found nothing is stored (empty list); one that failed
    is not, so the next task retries."""
    if school is None:
        return None, []
    if (
        school.institution_names is not None
        or not settings.openalex_resolve_institutions
    ):
        return stored(school)
    try:
        found = await openalex.find_institution(school.name)
    except (openalex.OpenAlexUnavailable, httpx.HTTPError):
        return None, []
    school.openalex_institution_id = found["id"] if found else None
    school.institution_names = json.dumps(found["names"] if found else [])
    # The top hit is kept for good: log it to spot wrong resolutions.
    log.info(
        "school %r resolved to OpenAlex institution %s (%s)",
        school.name,
        found["id"] if found else None,
        (found["names"] or ["-"])[0] if found else "no match",
    )
    await session.commit()
    return stored(school)
