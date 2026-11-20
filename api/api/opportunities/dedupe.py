"""Duplicate detection: the catalogue key, organization aliases and near-duplicate pairs.

The key is normalized organization plus normalized title. Normalizing strips what changes
between cycles of one scheme (years, "call for applications", "cohort 5") and the generic
words organizations add or drop ("Wellcome" and "Wellcome Trust"), so a new cycle refreshes
the existing row instead of creating a second one. Names that differ in other ways
("DAAD" and "German Academic Exchange Service") are mapped by the alias table.

Anything the key cannot catch shows up in the staff "possible duplicates" list, which pairs
listings by trigram title similarity (pg_trgm) and by shared source page.
"""

import re

from sqlalchemy import select, text, update

from api.opportunities.models import OrganizationAlias

_PUNCTUATION = re.compile(r"[^a-z0-9 ]")
_SPACES = re.compile(r"\s+")

# "2026", "2026/27", "2026-2027": the cycle, not the scheme. Read before punctuation goes.
_YEARS = re.compile(r"\b(?:19|20)\d{2}(?:\s*[/-]\s*(?:19|20)?\d{2})?\b")
_ORDINAL = r"(?:\d+(?:st|nd|rd|th)?|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)"
_CYCLE_WORDS = r"(?:call|cohort|round|intake|edition|cycle|batch)"
_CYCLE_PHRASES = (
    re.compile(
        r"\b(?:open )?call for (?:applications|proposals|entries|nominations|submissions|participants)\b"
    ),
    re.compile(r"\b(?:applications? (?:are )?(?:now )?open|now open|apply now)\b"),
    re.compile(rf"\b(?:{_ORDINAL} )?{_CYCLE_WORDS}(?: {_ORDINAL})?\b"),
)
# Words organizations add or drop without naming anyone else.
_ORG_FILLER = {
    "foundation",
    "trust",
    "fund",
    "inc",
    "incorporated",
    "ltd",
    "limited",
    "llc",
    "plc",
    "gmbh",
    "org",
    "organisation",
    "organization",
}


def normalize(value: str) -> str:
    return _SPACES.sub(" ", _PUNCTUATION.sub(" ", (value or "").lower())).strip()


def title_key(title: str) -> str:
    """The title without its cycle: falls back to the plain title if nothing is left."""
    plain = normalize(title)
    stripped = normalize(_YEARS.sub(" ", (title or "").lower()))
    for pattern in _CYCLE_PHRASES:
        stripped = pattern.sub(" ", stripped)
    stripped = _SPACES.sub(" ", stripped).strip()
    return stripped or plain


def organization_key(organization: str, aliases: dict[str, str] | None = None) -> str:
    words = normalize(organization).split()
    if words[:1] == ["the"]:
        words = words[1:]
    while len(words) > 1 and words[-1] in _ORG_FILLER:
        words.pop()
    root = " ".join(words)
    return (aliases or {}).get(root, root)


def dedupe_key(
    organization: str, title: str, aliases: dict[str, str] | None = None
) -> str:
    return f"{organization_key(organization, aliases)}|{title_key(title)}"


async def load_aliases(session) -> dict[str, str]:
    """{alias root: canonical root}; a small table read once per save."""
    rows = await session.execute(
        select(OrganizationAlias.alias, OrganizationAlias.canonical)
    )
    return dict(rows.all())


async def key_for(session, organization: str, title: str) -> str:
    return dedupe_key(organization, title, await load_aliases(session))


#: Title similarity (0 to 1) from which two listings count as possible duplicates.
SIMILARITY = 0.5

_SIMILAR_TITLES = text(
    """
    SELECT a.id AS first_id, b.id AS second_id,
           similarity(lower(a.title), lower(b.title)) AS score,
           'similar_title' AS reason
    FROM opportunities a
    JOIN opportunities b
      ON a.id < b.id AND lower(a.title) % lower(b.title)
    WHERE a.status <> 'hidden' AND b.status <> 'hidden'
      AND similarity(lower(a.title), lower(b.title)) >= :threshold
      AND (
        split_part(a.dedupe_key, '|', 1) = split_part(b.dedupe_key, '|', 1)
        OR a.organization = '' OR b.organization = ''
        OR similarity(lower(a.organization), lower(b.organization)) >= 0.6
      )
      AND NOT EXISTS (
        SELECT 1 FROM duplicate_dismissals d
        WHERE d.first_id = a.id AND d.second_id = b.id
      )
    ORDER BY score DESC, a.id, b.id
    LIMIT :limit
    """
)

_SHARED_PAGES = text(
    """
    SELECT a.id AS first_id, b.id AS second_id, 1.0 AS score,
           'same_page' AS reason
    FROM opportunities a
    JOIN opportunities b
      ON a.id < b.id AND a.source_url <> '' AND a.source_url = b.source_url
    WHERE a.status <> 'hidden' AND b.status <> 'hidden'
      AND NOT EXISTS (
        SELECT 1 FROM duplicate_dismissals d
        WHERE d.first_id = a.id AND d.second_id = b.id
      )
    ORDER BY a.id, b.id
    LIMIT :limit
    """
)


async def possible_duplicates(session, limit: int = 50) -> list[dict]:
    """Pairs most likely to be one opportunity, best first; dismissed pairs excluded."""
    pairs: dict[tuple[str, str], dict] = {}
    for query in (_SHARED_PAGES, _SIMILAR_TITLES):
        rows = await session.execute(query, {"threshold": SIMILARITY, "limit": limit})
        for row in rows.mappings():
            pair = (row["first_id"], row["second_id"])
            if pair not in pairs:
                pairs[pair] = {
                    "first_id": row["first_id"],
                    "second_id": row["second_id"],
                    "score": round(float(row["score"]), 3),
                    "reason": row["reason"],
                }
    return sorted(pairs.values(), key=lambda p: -p["score"])[:limit]


def ordered_pair(first_id: str, second_id: str) -> tuple[str, str]:
    return (first_id, second_id) if first_id < second_id else (second_id, first_id)


async def rekey_organization(session, *roots: str) -> int:
    """Recompute keys of listings whose organization is one of `roots` (before aliases).

    Run after an alias changes. A listing whose new key another listing already holds keeps
    its old key: the pair then shows in the possible-duplicates list for staff to merge.
    Returns how many listings changed key.
    """
    from api.opportunities.models import Opportunity

    wanted = set(roots)
    aliases = await load_aliases(session)
    rows = (
        await session.execute(
            select(
                Opportunity.id,
                Opportunity.organization,
                Opportunity.title,
                Opportunity.dedupe_key,
            )
        )
    ).all()
    taken = {row.dedupe_key for row in rows}
    changed = 0
    for row in rows:
        if organization_key(row.organization) not in wanted:
            continue
        key = dedupe_key(row.organization, row.title, aliases)
        if key == row.dedupe_key or key in taken:
            continue
        await session.execute(
            update(Opportunity)
            .where(Opportunity.id == row.id)
            .values(dedupe_key=key)
            .execution_options(synchronize_session=False)
        )
        taken.discard(row.dedupe_key)
        taken.add(key)
        changed += 1
    return changed
