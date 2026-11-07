"""OpenAlex: structured publication records instead of scraping homepages.

Priced per request: without OPENALEX_API_KEY every caller on the same IP
shares one small daily budget.
"""

import asyncio
import copy
import json
import logging
import re
from datetime import UTC, date, datetime, timedelta

import httpx

from api.core.config import settings
from api.core.textnorm import normalize_text
from api.core.ttlcache import TTLCache

BASE_URL = "https://api.openalex.org"
log = logging.getLogger(__name__)


def _headers() -> dict:
    """The contact address is the operator's (OPENALEX_MAILTO), never a placeholder."""
    contact = settings.openalex_mailto.strip()
    agent = f"graduator (mailto:{contact})" if contact else "graduator"
    headers = {"User-Agent": agent}
    key = settings.openalex_api_key.strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


# Process-wide, built lazily: a Semaphore binds to the loop that first awaits it.
_OPENALEX_SEM: asyncio.Semaphore | None = None

# Shared so calls reuse the keep-alive connection.
_client: httpx.AsyncClient | None = None


def _sem() -> asyncio.Semaphore:
    global _OPENALEX_SEM
    if _OPENALEX_SEM is None:
        _OPENALEX_SEM = asyncio.Semaphore(max(1, settings.openalex_concurrency))
    return _OPENALEX_SEM


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            headers=_headers(),
            timeout=20,
            limits=httpx.Limits(
                max_connections=max(1, settings.openalex_concurrency),
                keepalive_expiry=60.0,
            ),
        )
    return _client


def _reconstruct_abstract(inverted_index: dict | None) -> str | None:
    """Plain text from OpenAlex's inverted index (word -> positions)."""
    if not inverted_index:
        return None
    positions: dict[int, str] = {}
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))


class OpenAlexUnavailable(RuntimeError):
    """OpenAlex failed after retries; message tells the agent how to proceed."""


class OpenAlexWait(OpenAlexUnavailable):
    """No call can succeed until `until` (UTC), so professor tasks wait.
    Callers that degrade on an outage still catch it as OpenAlexUnavailable."""

    #: "budget" | "auth"
    reason = ""
    #: Shown to the task board while professor tasks wait.
    waiting_note = ""
    #: What a waiting task's model reads once it resumes.
    resumed_note = ""

    def __init__(self, until: datetime, message: str):
        super().__init__(message)
        self.until = until


class OpenAlexBudgetExhausted(OpenAlexWait):

    reason = "budget"
    waiting_note = "its daily budget is used up"
    resumed_note = "OpenAlex's daily budget ran out, so this task waited for it to reset"

    def __init__(self, until: datetime):
        super().__init__(
            until,
            f"OpenAlex's daily budget is used up until {until:%H:%M} UTC. Don't invent "
            "papers and don't retry OpenAlex in this task: save the professor with "
            "unverified: true and say their publications couldn't be checked, or conclude.",
        )


class OpenAlexAuthError(OpenAlexWait):
    """401/403 on the server's key; rechecked every OPENALEX_AUTH_RECHECK_SECONDS."""

    reason = "auth"
    waiting_note = "the server's API key was rejected"
    resumed_note = "OpenAlex rejected the server's API key, so this task waited until it was accepted"

    def __init__(self, until: datetime, status: int = 401):
        super().__init__(
            until,
            f"OpenAlex rejected the server's API key (HTTP {status}). Don't invent papers and "
            "don't retry OpenAlex in this task: save the professor with unverified: true and "
            "say their publications couldn't be checked, or conclude.",
        )
        self.status = status


_RETRY_DELAYS = (0.5, 1.5)
#: A 429 asking for a longer wait than this is the daily budget, not the
#: per-second limit: waiting in the request would only hold the slot.
BUDGET_RETRY_AFTER_SECONDS = 30.0

#: Process-wide breaker: fail at once instead of spending a request on a
#: certain failure. _down_reason says why.
_down_until: datetime | None = None
_down_reason: str = ""
#: The last budget headers OpenAlex sent.
_budget: dict = {}


def down_until() -> datetime | None:
    """When OpenAlex can be tried again (UTC) while the breaker is open, else None."""
    global _down_until, _down_reason
    if _down_until is not None and _down_until <= datetime.now(UTC):
        _down_until = None
        _down_reason = ""
    return _down_until


def wait_error() -> OpenAlexWait | None:
    """The breaker's state as the exception a caller raises, or None."""
    until = down_until()
    if until is None:
        return None
    if _down_reason == "auth":
        return OpenAlexAuthError(until)
    return OpenAlexBudgetExhausted(until)


def budget() -> dict:
    """What OpenAlex last said about the daily budget, plus the breaker."""
    until = down_until()
    return {**_budget, "keyed": bool(settings.openalex_api_key.strip()), "down_until": until}


def _trip(until: datetime, reason: str = "budget") -> None:
    global _down_until, _down_reason
    if reason == "auth" and _down_reason != "auth":
        # Once per trip, not per request: an operator has to fix this.
        log.error(
            "OpenAlex rejected the API key; professor research is waiting. "
            "Check OPENALEX_API_KEY (rechecked every %ss).",
            settings.openalex_auth_recheck_seconds,
        )
    if _down_until is None or until > _down_until or reason != _down_reason:
        _down_until = until
        _down_reason = reason


def reset_breaker() -> None:
    """Close the breaker and forget the budget (tests)."""
    global _down_until, _down_reason
    _down_until = None
    _down_reason = ""
    _budget.clear()


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _next_midnight(now: datetime) -> datetime:
    return datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), UTC)


def _reset_at(resp: httpx.Response, now: datetime) -> datetime | None:
    """X-RateLimit-Reset as a time: epoch seconds or seconds from now."""
    value = _float(resp.headers.get("x-ratelimit-reset"))
    if value is None or value <= 0:
        return None
    if value > 1e9:
        return datetime.fromtimestamp(value, UTC)
    return now + timedelta(seconds=value)


def _note_budget(resp: httpx.Response) -> None:
    """Keep the budget headers; trip the breaker once nothing is left."""
    remaining = _float(resp.headers.get("x-ratelimit-remaining-usd"))
    if remaining is None:
        return
    now = datetime.now(UTC)
    reset = _reset_at(resp, now)
    _budget.update(
        {
            "remaining_usd": remaining,
            "limit_usd": _float(resp.headers.get("x-ratelimit-limit-usd")),
            "resets_at": reset,
            "seen_at": now,
        }
    )
    if remaining <= 0:
        _trip(_budget_reset(resp, now))


def _long_retry_after(resp: httpx.Response, now: datetime) -> datetime | None:
    """Retry-After as a time, when it's too long to wait out in a request."""
    retry_after = _float(resp.headers.get("retry-after"))
    if retry_after is not None and retry_after > BUDGET_RETRY_AFTER_SECONDS:
        return now + timedelta(seconds=retry_after)
    return None


def _budget_reset(resp: httpx.Response, now: datetime) -> datetime:
    """Retry-After, else X-RateLimit-Reset, else next UTC midnight. Shared by the
    budget headers and the 429 so the breaker never outwaits the server's ask."""
    return _long_retry_after(resp, now) or _reset_at(resp, now) or _next_midnight(now)


def _budget_wait(resp: httpx.Response) -> datetime | None:
    """For a 429: the daily budget's reset, or None for a short per-second limit."""
    now = datetime.now(UTC)
    until = _long_retry_after(resp, now)
    if until is not None:
        return until
    remaining = _float(resp.headers.get("x-ratelimit-remaining-usd"))
    if remaining is not None and remaining <= 0:
        return _budget_reset(resp, now)
    return None


_RESPONSES: TTLCache[dict] = TTLCache(512, lambda: settings.openalex_cache_seconds)


async def _get_json(path: str, params: dict, *, long_lived: bool = False) -> dict:
    """GET with bounded retries. Successes are cached in process and in Postgres
    (the long TTL for `long_lived` data); failures never are."""
    key = path + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
    cached = _RESPONSES.get(key)
    if cached is not None:
        return copy.deepcopy(cached)  # callers own what they get back
    stored = await _db_get(key)
    if stored is not None:
        _RESPONSES.put(key, copy.deepcopy(stored))
        return stored
    data = await _fetch_json(path, params)
    _RESPONSES.put(key, copy.deepcopy(data))
    days = settings.openalex_db_cache_long_days if long_lived else settings.openalex_db_cache_days
    await _db_put(key, data, days)
    return data


async def _db_get(key: str) -> dict | None:
    """A stored, unexpired response, or None; any read failure is a miss."""
    if settings.openalex_db_cache_days <= 0:
        return None
    from api.core.db import SessionLocal
    from api.prospects.models import OpenAlexResponse

    try:
        async with SessionLocal() as session:
            row = await session.get(OpenAlexResponse, key)
            if row is None or row.expires_at <= datetime.now(UTC).replace(tzinfo=None):
                return None
            return json.loads(row.body)
    except Exception:  # noqa: BLE001 - a cache miss, never a failed lookup
        return None


async def prune_stored_responses(session) -> int:
    """Delete stored responses past their expiry (the worker's reaper)."""
    from sqlalchemy import delete

    from api.prospects.models import OpenAlexResponse

    result = await session.execute(
        delete(OpenAlexResponse).where(
            OpenAlexResponse.expires_at <= datetime.now(UTC).replace(tzinfo=None)
        )
    )
    await session.commit()
    return result.rowcount or 0


async def _db_put(key: str, data: dict, days: int) -> None:
    if settings.openalex_db_cache_days <= 0 or days <= 0:
        return
    from sqlalchemy.dialects.postgresql import insert

    from api.core.db import SessionLocal
    from api.prospects.models import OpenAlexResponse

    now = datetime.now(UTC).replace(tzinfo=None)
    values = {
        "key": key,
        "body": json.dumps(data),
        "fetched_at": now,
        "expires_at": now + timedelta(days=days),
    }
    try:
        async with SessionLocal() as session:
            await session.execute(
                insert(OpenAlexResponse)
                .values(**values)
                .on_conflict_do_update(index_elements=["key"], set_=values)
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001 - the lookup itself succeeded
        log.info("openalex cache write skipped: %s", type(exc).__name__)


#: Also used by the other public sources, under their own keys.
stored_response, store_response = _db_get, _db_put


async def _fetch_json(path: str, params: dict) -> dict:
    last: str = ""
    for attempt in range(len(_RETRY_DELAYS) + 1):
        waiting = wait_error()
        if waiting is not None:
            raise waiting
        wait = _RETRY_DELAYS[attempt] if attempt < len(_RETRY_DELAYS) else 0.0
        try:
            async with _sem():
                resp = await client().get(f"{BASE_URL}{path}", params=params)
            _note_budget(resp)
            if resp.status_code == 429:
                until = _budget_wait(resp)
                if until is not None:
                    _trip(until)
                    raise OpenAlexBudgetExhausted(until)
                last = "HTTP 429"
                wait = max(wait, _float(resp.headers.get("retry-after")) or 0.0)
            elif resp.status_code in (401, 403):
                # A wrong, revoked or unfunded key: every call will fail
                # until someone fixes it, so open the breaker.
                until = datetime.now(UTC) + timedelta(
                    seconds=max(1, settings.openalex_auth_recheck_seconds)
                )
                _trip(until, "auth")
                raise OpenAlexAuthError(until, resp.status_code)
            elif resp.status_code >= 500:
                last = f"HTTP {resp.status_code}"
            else:
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError:
            raise
        except httpx.HTTPError as exc:
            last = type(exc).__name__
        if attempt < len(_RETRY_DELAYS):
            await asyncio.sleep(wait)
    raise OpenAlexUnavailable(
        f"OpenAlex is unavailable right now ({last}). Don't invent papers: either try again "
        "later in this task, or save the professor with unverified: true and say in the "
        "rationale that their publications couldn't be checked."
    )


#: Affiliations this recent still count as the author's institutions.
RECENT_AFFILIATION_YEARS = 5
_HONORIFIC = re.compile(r"^(prof(essor)?|dr|mr|mrs|ms|mx)\.?\s+", re.IGNORECASE)
_DEGREES = re.compile(r",?\s+(ph\.?\s?d|m\.?d|m\.?sc|dphil)\.?$", re.IGNORECASE)


def clean_person_name(name: str) -> str:
    """ "Prof. Dr. Jane Smith, PhD" -> "Jane Smith"."""
    cleaned = name.strip()
    while True:
        stripped = _HONORIFIC.sub("", cleaned)
        if stripped == cleaned:
            break
        cleaned = stripped
    return _DEGREES.sub("", cleaned).strip(" ,")


def _short_id(value: str | None) -> str:
    return (value or "").rstrip("/").rsplit("/", 1)[-1].upper()


def author_institutions(record: dict) -> list[dict]:
    """last_known_institutions[] (the singular field is deprecated), then recent
    affiliations, as {"id", "name", "lineage"} with short ids."""
    seen: dict[str, dict] = {}

    def add(inst: dict | None) -> None:
        if not isinstance(inst, dict) or not inst.get("display_name"):
            return
        key = _short_id(inst.get("id")) or inst["display_name"].lower()
        if key not in seen:
            seen[key] = {
                "id": _short_id(inst.get("id")) or None,
                "name": inst["display_name"],
                "lineage": [_short_id(x) for x in inst.get("lineage") or [] if x],
            }

    for inst in record.get("last_known_institutions") or []:
        add(inst)
    add(record.get("last_known_institution"))
    this_year = datetime.now(UTC).year
    for aff in record.get("affiliations") or []:
        years = [y for y in aff.get("years") or [] if isinstance(y, int)]
        if not years or max(years) >= this_year - RECENT_AFFILIATION_YEARS:
            add(aff.get("institution"))
    return list(seen.values())


def _candidate(record: dict) -> dict:
    institutions = author_institutions(record)
    ids = {i["id"] for i in institutions if i["id"]}
    ids |= {x for i in institutions for x in i["lineage"]}
    return {
        "openalex_id": record["id"],
        "display_name": record["display_name"],
        "institution": institutions[0]["name"] if institutions else None,
        "institutions": [i["name"] for i in institutions],
        "institution_ids": sorted(ids),
        "works_count": record.get("works_count"),
        # What they work on, to tell same-name authors apart.
        "topics": [t.get("display_name") for t in (record.get("topics") or [])[:5] if t.get("display_name")],
    }


_ROSTER_FIELDS = "id,display_name,display_name_alternatives,last_known_institutions,affiliations,works_count,topics"
_ROSTER_PAGE = 200


async def school_authors(institution_id: str) -> list[dict]:
    """The school's authors, most published first: list calls cost a tenth of a
    search, and faculty publish most so the first pages hold them."""
    authors: list[dict] = []
    for page in range(1, max(0, settings.openalex_roster_pages) + 1):
        try:
            data = await _get_json(
                "/authors",
                {
                    "filter": f"last_known_institutions.id:{_short_id(institution_id)}",
                    "sort": "works_count:desc",
                    "per_page": _ROSTER_PAGE,
                    "page": page,
                    "select": _ROSTER_FIELDS,
                },
                long_lived=True,
            )
        except httpx.HTTPStatusError:
            break  # a refused list call: searching by name still works
        results = data.get("results") or []
        authors.extend(results)
        if len(results) < _ROSTER_PAGE:
            break
    return authors


def _name_tokens(text: str | None) -> list[str]:
    return [t for t in normalize_text(text).split() if len(t) > 1]


def roster_matches(name: str, roster: list[dict]) -> list[dict]:
    """Authors whose name or alternatives hold the first and last names, in any
    order, ignoring accents, middle names and initials."""
    tokens = _name_tokens(clean_person_name(name) or name)
    if len(tokens) < 2:
        return []
    wanted = {tokens[0], tokens[-1]}
    return [
        author
        for author in roster
        if any(
            wanted <= set(_name_tokens(n))
            for n in [author.get("display_name"), *(author.get("display_name_alternatives") or [])]
            if n
        )
    ]


def name_variants(name: str) -> list[str]:
    """Up to two other spellings: "Smith, Jane" flipped, middle names dropped, or a
    two-part name reversed (family name first, as many East Asian names are listed)."""
    cleaned = " ".join(name.split())
    out: list[str] = []
    if cleaned.count(",") == 1:
        family, given = (p.strip() for p in cleaned.split(","))
        if family and given:
            out.append(f"{given} {family}")
            cleaned = f"{given} {family}"
    parts = cleaned.replace(",", " ").split()
    if len(parts) > 2:
        out.append(f"{parts[0]} {parts[-1]}")
    elif len(parts) == 2:
        out.append(f"{parts[1]} {parts[0]}")
    def key(text: str) -> str:
        return " ".join(text.replace(",", " ").lower().split())

    seen = {key(name)}
    variants = []
    for v in out:
        if key(v) not in seen:
            seen.add(key(v))
            variants.append(v)
    return variants[:2]


async def find_author(
    name: str,
    institution_hint: str | None = None,
    institution_id: str | None = None,
) -> list[dict]:
    """School author list first, then a search within the institution (a common
    name's right person is often not in the global top 5), then globally."""
    query = clean_person_name(name) or name
    results: list[dict] = []
    if institution_id and settings.openalex_roster_pages > 0:
        # List calls, cached per school, are cheaper than a search per professor.
        results = roster_matches(query, await school_authors(institution_id))[:5]
    if institution_id and not results:
        for spelling in [query, *name_variants(query)]:
            results = (
                await _get_json(
                    "/authors",
                    {
                        "search": spelling,
                        "filter": f"affiliations.institution.id:{_short_id(institution_id)}",
                        "per_page": 5,
                    },
                )
            ).get("results", [])
            if results:
                break
    if not results:
        results = (await _get_json("/authors", {"search": query, "per_page": 5})).get(
            "results", []
        )
    candidates = [_candidate(r) for r in results]

    if institution_hint:
        hint = institution_hint.lower()
        candidates.sort(
            key=lambda c: not any(hint in n.lower() for n in c["institutions"])
        )
    return candidates


async def find_author_by_orcid(orcid: str) -> list[dict]:
    """A filter, billed as a list call rather than a search."""
    data = await _get_json("/authors", {"filter": f"orcid:{orcid}", "per_page": 2})
    return [_candidate(r) for r in data.get("results") or []]


async def find_institution(name: str) -> dict | None:
    """{"id", "display_name", "names"} or None."""
    results = (
        await _get_json("/institutions", {"search": name, "per_page": 1}, long_lived=True)
    ).get(
        "results", []
    )
    if not results:
        return None
    top = results[0]
    names = [top.get("display_name") or ""]
    names += list(top.get("display_name_alternatives") or [])
    names += list(top.get("display_name_acronyms") or [])
    return {
        "id": _short_id(top.get("id")),
        "display_name": top.get("display_name"),
        "names": [n for n in dict.fromkeys(names) if n],
    }


def years_before(day: date, years: int) -> date:
    """The same day `years` back, with 29 February falling to the 28th."""
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


async def authors_publishing_on(
    institution_id: str, query: str, years: int = 5, limit: int = 200
) -> list[dict]:
    """[{"openalex_id", "name", "works"}], most works first. Includes coauthors
    from elsewhere; callers intersect with the faculty list."""
    since = years_before(datetime.now(UTC).date(), years).isoformat()
    data = await _get_json(
        "/works",
        {
            "filter": f"institutions.id:{institution_id},from_publication_date:{since}",
            "search": query,
            "group_by": "authorships.author.id",
            "per_page": limit,
        },
    )
    out = []
    for group in data.get("group_by") or []:
        key = str(group.get("key") or "")
        if not key:
            continue
        out.append(
            {
                "openalex_id": key.rsplit("/", 1)[-1],
                "name": group.get("key_display_name") or "",
                "works": int(group.get("count") or 0),
            }
        )
    return sorted(out, key=lambda a: a["works"], reverse=True)


async def get_recent_works(
    openalex_author_id: str, limit: int = 15, years: int | None = None
) -> list[dict]:
    """Most recent works with abstracts; `years` bounds by date rather than count
    so a prolific author's one aligned paper isn't missed."""
    filters = [f"author.id:{openalex_author_id}"]
    if years:
        since = years_before(datetime.now(UTC).date(), years)
        filters.append(f"from_publication_date:{since.isoformat()}")
    params = {
        "filter": ",".join(filters),
        "sort": "publication_date:desc",
        "per_page": limit,
    }
    results = (await _get_json("/works", params)).get("results", [])

    works = []
    for w in results:
        works.append(
            {
                "title": w.get("title"),
                "abstract": _reconstruct_abstract(w.get("abstract_inverted_index")),
                "year": w.get("publication_year"),
                "venue": ((w.get("primary_location") or {}).get("source") or {}).get(
                    "display_name"
                ),
                "url": (w.get("primary_location") or {}).get("landing_page_url")
                or w.get("id"),
                "citations": w.get("cited_by_count"),
                "publication_type": _publication_type(w),
                "coauthors": _coauthors(w, openalex_author_id),
            }
        )
    return works


def _publication_type(work: dict) -> str | None:
    raw = work.get("raw_type") or work.get("type_crossref")
    if raw in {"proceedings-article", "journal-article"}:
        return "conference-paper" if raw == "proceedings-article" else raw
    kind = work.get("type")
    source = ((work.get("primary_location") or {}).get("source") or {}).get("type")
    if kind == "article" and source in {"conference", "journal"}:
        return "conference-paper" if source == "conference" else "journal-article"
    return kind or None


#: Co-authors kept per paper; large collaborations list hundreds.
MAX_COAUTHORS = 12


def _coauthors(work: dict, author_id: str) -> list[dict]:
    """The work's other authors, in byline order."""
    own = author_id.rsplit("/", 1)[-1]
    out = []
    for a in work.get("authorships") or []:
        author = a.get("author") or {}
        short = str(author.get("id") or "").rsplit("/", 1)[-1] or None
        if short == own or not author.get("display_name"):
            continue
        out.append({"name": author["display_name"], "openalex_id": short})
    return out[:MAX_COAUTHORS]


def brief_works(works: list[dict]) -> list[dict]:
    """Abstracts cut for the model; scoring and saving use the full recorded works."""
    chars = max(40, settings.works_abstract_chars)
    out = []
    for w in works:
        abstract = w.get("abstract")
        if abstract and len(abstract) > chars:
            abstract = abstract[:chars].rsplit(" ", 1)[0] + "…"
        # Co-author lists are for the student, not worth the model's tokens.
        out.append({**{k: v for k, v in w.items() if k != "coauthors"}, "abstract": abstract})
    return out
