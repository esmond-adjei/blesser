"""Faculty lists mostly in code, to spare the supervisor's agent loop.

1. a stored roster (kept FACULTY_ROSTER_DAYS);
2. the department page, then /people or /faculty beside it, one
   extraction call per page;
3. only with too few names, the supervisor's agent loop;
4. failing that, OpenAlex authors at the school publishing on the topic.

Names go through spawn_professor_research either way, so ranking,
opt-outs, fair share and caps still apply.
"""

import json
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from api.core.config import settings
from api.prospects import web

_LISTING_PATHS = ("people", "faculty")
_NAME = re.compile(r"^[^\W\d_][\w.'’\- ]{2,80}$")


def roster_key(url: str | None) -> str | None:
    """Host and path, lowercased, without scheme, query or trailing slash."""
    if not url:
        return None
    parts = urlsplit(url.strip())
    if not parts.netloc:
        return None
    host = parts.netloc.lower().removeprefix("www.")
    return f"{host}{parts.path.rstrip('/').lower()}"


def listing_urls(url: str) -> list[str]:
    base = url.strip().rstrip("/")
    return [url.strip(), *(f"{base}/{p}" for p in _LISTING_PATHS)]


def parse_names(text: str | None) -> list[str]:
    """A JSON array of strings or {"name"} anywhere in the reply; non-names dropped, order kept."""
    if not text:
        return []
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        raw = json.loads(text[start : end + 1])
    except ValueError:
        return []
    names: list[str] = []
    for item in raw if isinstance(raw, list) else []:
        name = item.get("name") if isinstance(item, dict) else item
        if isinstance(name, str):
            name = " ".join(name.split())
            if _NAME.match(name) and " " in name and name not in names:
                names.append(name)
    return names


async def stored(session, key: str | None) -> list[str]:
    from api.prospects.models import FacultyRoster

    if key is None or settings.faculty_roster_days <= 0:
        return []
    row = await session.get(FacultyRoster, key)
    if row is None or row.expires_at <= datetime.now(UTC).replace(tzinfo=None):
        return []
    try:
        names = json.loads(row.names)
    except ValueError:
        return []
    return [n for n in names if isinstance(n, str)]


async def store(session, key: str | None, names: list[str], source: str) -> None:
    from sqlalchemy.dialects.postgresql import insert

    from api.prospects.models import FacultyRoster

    if key is None or not names or settings.faculty_roster_days <= 0:
        return
    now = datetime.now(UTC).replace(tzinfo=None)
    values = {
        "key": key,
        "names": json.dumps(names),
        "source": source,
        "fetched_at": now,
        "expires_at": now + timedelta(days=settings.faculty_roster_days),
    }
    await session.execute(
        insert(FacultyRoster).values(**values).on_conflict_do_update(index_elements=["key"], set_=values)
    )


async def fetch_listing(url: str) -> str | None:
    text = await web.fetch_page(url, max_chars=settings.roster_page_chars)
    if not text or text.startswith("[Could not fetch"):
        return None
    return text


async def openalex_seed(institution_id: str | None, interest: str, limit: int) -> list[str]:
    """Last resort: OpenAlex authors at the school publishing on the topic, most works first."""
    from api.prospects import openalex, ranking

    query = ranking.topic_query(interest)
    if not institution_id or not query or limit <= 0:
        return []
    try:
        topical = await openalex.authors_publishing_on(institution_id, query)
        current = {
            openalex._short_id(a.get("id"))
            for a in await openalex.school_authors(institution_id)
        }
    except Exception:  # noqa: BLE001 - a last resort; nothing to seed then
        return []
    names = [
        a["name"]
        for a in topical
        if a["works"] >= settings.roster_seed_min_works and a["openalex_id"].upper() in current and a["name"]
    ]
    return names[:limit]
