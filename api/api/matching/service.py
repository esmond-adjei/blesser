"""Match profiles: storage, prefill from the Applicant Kit, and the SQL that scores
listings against them.

Scoring is plain SQL so "For you" pages, alerts and counts all agree:

- Gate: a listing whose `countries` names only specific countries, none of them
  the member's, is left out. Regions, "Global" and empty lists stay in.
- Score: category 3, kind 2, each field of study or sector found in the listing
  1.5 (at most 3 count), a stage word 1, closing in 7 to 30 days 1 (0 to 6 days
  0.5), verified in the last 30 days 0.5, added in the last 7 days 0.5.
- Fit (alerts): passes the gate and matches every kind of preference the member
  set among categories, kinds and fields.
"""

import re
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import (
    Float,
    String,
    and_,
    bindparam,
    case,
    cast,
    false,
    func,
    literal,
    or_,
    select,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import ARRAY, array

from api.core.time import utcnow_naive
from api.matching import geo
from api.matching import models as mm
from api.opportunities import models as om

CATEGORIES = tuple(c.value for c in om.OpportunityCategory)
KINDS = tuple(k.value for k in om.OpportunityKind)

#: Stage words, as to_tsquery expressions over the listing text.
LEVELS = {
    "undergraduate": "undergraduate | bachelor | bachelors | undergrad",
    "masters": "master | masters | msc | mba | postgraduate",
    "phd": "phd | doctoral | doctorate",
    "postdoc": "postdoc | postdoctoral | researcher | faculty",
    "founder": "startup | founder | entrepreneur | venture | sme",
}

MAX_FIELDS = 12
#: Field terms that count towards the score (the first ones the member listed).
SCORED_FIELDS = 8
FIELD_WEIGHT = 1.5
FIELD_CAP = 3.0


@dataclass(frozen=True)
class Prefs:
    categories: tuple[str, ...] = ()
    kinds: tuple[str, ...] = ()
    fields: tuple[str, ...] = ()
    levels: tuple[str, ...] = ()
    countries: tuple[str, ...] = ()

    @property
    def empty(self) -> bool:
        return not (self.categories or self.kinds or self.fields or self.levels or self.countries)

    @property
    def can_alert(self) -> bool:
        """Alerts need something to match on, not only a country."""
        return bool(self.categories or self.kinds or self.fields)


def prefs_of(row: mm.MatchProfile | None) -> Prefs:
    if row is None:
        return Prefs()
    return Prefs(
        categories=tuple(c for c in row.categories or [] if c in CATEGORIES),
        kinds=tuple(k for k in row.kinds or [] if k in KINDS),
        fields=tuple(row.fields or [])[:MAX_FIELDS],
        levels=tuple(lv for lv in row.levels or [] if lv in LEVELS),
        countries=tuple(row.countries or []),
    )


# --- SQL pieces -------------------------------------------------------------

_NORM_SQL = (
    "btrim(regexp_replace(regexp_replace(lower(replace(c.value, 'ô', 'o')), "
    "'[^a-z0-9 ]', ' ', 'g'), '\\s+', ' ', 'g'))"
)


def country_gate(prefs: Prefs):
    """True when the listing is open to someone from one of the member's countries."""
    mine = sorted({key for name in prefs.countries for key in geo.keys_for(name)})
    if not mine:
        return true()
    return text(
        "(CASE WHEN json_typeof(opportunities.countries) = 'array' "
        "AND json_array_length(opportunities.countries) > 0 THEN EXISTS ("
        "SELECT 1 FROM json_array_elements_text(opportunities.countries) AS c(value) "
        f"WHERE NOT ({_NORM_SQL} = ANY(:gate_known)) OR {_NORM_SQL} = ANY(:gate_mine)"
        ") ELSE true END)"
    ).bindparams(
        bindparam("gate_known", geo.known_keys(), type_=ARRAY(String)),
        bindparam("gate_mine", mine, type_=ARRAY(String)),
    )


def _hits(query):
    return om.Opportunity.search_vector.op("@@")(query)


def field_hits(prefs: Prefs) -> list[tuple[str, object]]:
    return [
        (term, _hits(func.plainto_tsquery("english", term)))
        for term in prefs.fields[:SCORED_FIELDS]
    ]


def level_hit(prefs: Prefs):
    if not prefs.levels:
        return None
    expr = " | ".join(f"({LEVELS[lv]})" for lv in prefs.levels)
    return _hits(func.to_tsquery("english", expr))


def score_columns(prefs: Prefs):
    """(score, matched field terms) as SQL columns."""
    o = om.Opportunity
    now = utcnow_naive()
    today = now.date()
    parts = [literal(0.0, Float)]
    if prefs.categories:
        parts.append(case((o.category.in_(prefs.categories), 3.0), else_=0.0))
    if prefs.kinds:
        parts.append(case((o.kind.in_(prefs.kinds), 2.0), else_=0.0))
    fields = field_hits(prefs)
    if fields:
        total = sum((case((hit, FIELD_WEIGHT), else_=0.0) for _, hit in fields), literal(0.0, Float))
        parts.append(func.least(total, FIELD_CAP))
    if (lv := level_hit(prefs)) is not None:
        parts.append(case((lv, 1.0), else_=0.0))
    parts.append(
        case(
            (o.deadline_date.between(today + timedelta(days=7), today + timedelta(days=30)), 1.0),
            (o.deadline_date.between(today, today + timedelta(days=6)), 0.5),
            else_=0.0,
        )
    )
    parts.append(case((o.verified_at >= now - timedelta(days=30), 0.5), else_=0.0))
    parts.append(case((o.created_at >= now - timedelta(days=7), 0.5), else_=0.0))
    score = sum(parts[1:], parts[0]).label("match_score")
    if fields:
        terms = func.array_remove(
            array([case((hit, literal(term, String)), else_=None) for term, hit in fields]),
            None,
        )
    else:
        terms = cast(array([], type_=String), ARRAY(String))
    return score, terms.label("match_terms")


def fit_clause(prefs: Prefs):
    """A good match for alerts: every kind of preference the member set agrees."""
    if not prefs.can_alert:
        return false()
    o = om.Opportunity
    clauses = [country_gate(prefs)]
    if prefs.categories:
        clauses.append(o.category.in_(prefs.categories))
    if prefs.kinds:
        clauses.append(o.kind.in_(prefs.kinds))
    if fields := field_hits(prefs):
        clauses.append(or_(*(hit for _, hit in fields)))
    return and_(*clauses)


# --- Search -----------------------------------------------------------------

_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def tsquery_text(q: str) -> str:
    """Each word as a stemmed prefix, all required: "scholar" finds "scholarships"."""
    return " & ".join(f"{word}:*" for word in _WORD.findall((q or "").lower())[:8])


def search_query(q: str):
    """The tsquery for a search box, or None when there are no words."""
    expr = tsquery_text(q)
    return func.to_tsquery("english", expr) if expr else None


def search_clause(query):
    # Only stop words ("the", "for"): Postgres drops them all; match everything.
    return or_(func.numnode(query) == 0, _hits(query))


def search_rank(query):
    return func.ts_rank_cd(om.Opportunity.search_vector, query)


# --- Profile storage and prefill ---------------------------------------------

_LEVEL_WORDS = (
    ("phd", re.compile(r"\b(ph\.?\s?d|doctor|doctoral|dphil)\b", re.IGNORECASE)),
    ("masters", re.compile(r"\b(master|masters|msc|m\.sc|ma|mba|mphil|meng|llm|mph)\b", re.IGNORECASE)),
    ("undergraduate", re.compile(r"\b(bachelor|bachelors|bsc|b\.sc|ba|beng|llb|undergraduate|degree)\b", re.IGNORECASE)),
)
_NEXT_LEVEL = {"undergraduate": "masters", "masters": "phd", "phd": "postdoc"}


def _clean(values, limit: int, max_len: int = 80) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        value = re.sub(r"\s+", " ", str(raw or "")).strip()[:max_len]
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            out.append(value)
        if len(out) >= limit:
            break
    return out


def clean_countries(values) -> list[str]:
    out: list[str] = []
    for value in values or []:
        name = geo.country(value)
        if name and name not in out:
            out.append(name)
    return out[:10]


def to_out(row: mm.MatchProfile | None, *, suggested: dict | None = None) -> dict:
    if row is None:
        base = suggested or {}
        return {
            "saved": False,
            "categories": base.get("categories", []),
            "kinds": base.get("kinds", []),
            "fields": base.get("fields", []),
            "levels": base.get("levels", []),
            "countries": base.get("countries", []),
            "alerts": "daily",
            "closing_soon": True,
            "updated_at": None,
        }
    return {
        "saved": True,
        "categories": list(row.categories or []),
        "kinds": list(row.kinds or []),
        "fields": list(row.fields or []),
        "levels": list(row.levels or []),
        "countries": list(row.countries or []),
        "alerts": row.alerts,
        "closing_soon": bool(row.closing_soon),
        "updated_at": row.updated_at,
    }


async def suggest(session, user_id: str) -> dict:
    """A starting profile from the Applicant Kit: countries, stage, fields and skills."""
    from api.applicant_kit.models import Profile

    kit = await session.get(Profile, user_id)
    data = (kit.data if kit else None) or {}
    countries = clean_countries([data.get("nationality"), data.get("country_of_residence")])
    education = [e for e in data.get("education") or [] if isinstance(e, dict)]
    # Most recent first: an open-ended entry is the one in progress.
    education.sort(key=lambda e: (e.get("end") is None, e.get("end") or "", e.get("start") or ""), reverse=True)
    levels: list[str] = []
    for entry in education[:1]:
        qualification = entry.get("qualification") or ""
        for level, pattern in _LEVEL_WORDS:
            if pattern.search(qualification):
                # Finished studies point at the next stage; ongoing ones at this one.
                levels.append(level if entry.get("end") is None else _NEXT_LEVEL.get(level, level))
                break
    fields = _clean([e.get("field") for e in education] + list(data.get("skills") or [])[:6], 8)
    categories: list[str] = []
    if levels and levels[0] in ("undergraduate", "masters", "phd"):
        categories.append("student")
    if levels and levels[0] in ("phd", "postdoc"):
        categories.append("research")
    return {"categories": categories, "kinds": [], "fields": fields, "levels": levels, "countries": countries}


async def get(session, user_id: str) -> mm.MatchProfile | None:
    return await session.get(mm.MatchProfile, user_id)


async def get_prefs(session, user_id: str) -> Prefs:
    return prefs_of(await get(session, user_id))


async def read(session, user_id: str) -> dict:
    row = await get(session, user_id)
    if row is not None:
        return to_out(row)
    return to_out(None, suggested=await suggest(session, user_id))


async def save(session, user_id: str, data: dict) -> dict:
    row = await get(session, user_id)
    if row is None:
        row = mm.MatchProfile(user_id=user_id)
        # Alerts start from now: nothing published before saving is "new" to them.
        row.last_alert_at = utcnow_naive()
        session.add(row)
    row.categories = [c for c in dict.fromkeys(data.get("categories") or []) if c in CATEGORIES]
    row.kinds = [k for k in dict.fromkeys(data.get("kinds") or []) if k in KINDS]
    row.fields = _clean(data.get("fields"), MAX_FIELDS)
    row.levels = [lv for lv in dict.fromkeys(data.get("levels") or []) if lv in LEVELS]
    row.countries = clean_countries(data.get("countries"))
    if row.alerts == "off" and data.get("alerts", "off") != "off":
        # Turning alerts back on starts from now, not from when they went off.
        row.last_alert_at = utcnow_naive()
    row.alerts = data.get("alerts", row.alerts or "daily")
    row.closing_soon = bool(data.get("closing_soon", True))
    await session.commit()
    await session.refresh(row)
    return to_out(row)


async def delete(session, user_id: str) -> None:
    row = await get(session, user_id)
    if row is not None:
        await session.delete(row)
        await session.commit()


def scored_select(prefs: Prefs, *filters):
    """SELECT opportunity, score, terms for listings that pass the gate."""
    score, terms = score_columns(prefs)
    return select(om.Opportunity, score, terms).where(country_gate(prefs), *filters)
