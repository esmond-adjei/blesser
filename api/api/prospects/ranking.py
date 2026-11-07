"""Research the best-aligned professors first.

Page order would spend the research budget on whoever is listed first, so
names are ordered by their count of the school's recent topical works per
OpenAlex; unmatched names keep page order after them. The faculty page
stays the source of truth for who is faculty.
"""

import logging
import re

import httpx

from api.core.config import settings
from api.core.textnorm import normalize_text
from api.prospects import institutions, openalex

log = logging.getLogger(__name__)

_STOP = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
    "i", "im", "in", "into", "is", "it", "its", "me", "my", "of", "on", "or",
    "our", "phd", "masters", "master", "msc", "degree", "program", "programme",
    "research", "interested", "interest", "interests", "study", "studies",
    "the", "their", "this", "to", "using", "want", "we", "with", "work",
    "working", "would", "like", "particularly", "especially", "focus",
    "focused", "area", "areas", "field", "fields", "university", "canada",
    "europe", "usa", "uk", "school", "schools", "about", "also", "can",
    "am", "do", "go", "he", "if", "no", "so", "up", "us",
}  # fmt: skip


def topic_query(interest: str, limit: int = 12) -> str:
    words: list[str] = []
    for word in normalize_text(interest).split():
        # Two letters is enough for "ai", "ml", "rl" or "cv".
        if len(word) < 2 or word in _STOP or word.isdigit() or word in words:
            continue
        words.append(word)
        if len(words) >= limit:
            break
    return " ".join(words)


def _name_key(name: str) -> tuple[str, str] | None:
    """(surname, first initial), tolerant of "Surname, Given" and accents."""
    cleaned = openalex.clean_person_name(name)
    if "," in cleaned:
        surname, _, given = cleaned.partition(",")
        cleaned = f"{given} {surname}"
    tokens = [t for t in re.split(r"[\s.]+", normalize_text(cleaned)) if t]
    if len(tokens) < 2:
        return None
    return tokens[-1], tokens[0][0]


def rank_names(names: list[str], authors: list[dict]) -> tuple[list[str], int]:
    """(`names` reordered, how many matched): most topical works first, the rest in order."""
    works: dict[tuple[str, str], int] = {}
    for author in authors:
        key = _name_key(author.get("name") or "")
        if key is not None:
            works[key] = max(works.get(key, 0), int(author.get("works") or 0))
    scored = [(works.get(_name_key(n) or ("", ""), 0), i, n) for i, n in enumerate(names)]
    ranked = sorted((s for s in scored if s[0] > 0), key=lambda s: (-s[0], s[1]))
    rest = [s for s in scored if s[0] == 0]
    return [n for _, _, n in ranked + rest], len(ranked)


async def rank_by_topic(session, school, interest: str, names: list[str]) -> tuple[list[str], bool]:
    """(names in research order, whether a topical ranking was applied)."""
    if not settings.openalex_rank_faculty or len(names) < 2 or school is None:
        return names, False
    query = topic_query(interest)
    if not query:
        return names, False
    institution_id, _ = await institutions.resolve_school(session, school)
    if not institution_id:
        return names, False
    try:
        authors = await openalex.authors_publishing_on(institution_id, query)
    except (openalex.OpenAlexUnavailable, httpx.HTTPError) as exc:
        log.info("topic ranking skipped for %r: %s", school.name, exc)
        return names, False
    ranked, matched = rank_names(names, authors)
    return ranked, matched > 0
