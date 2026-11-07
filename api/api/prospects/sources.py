"""Verifying professors beyond OpenAlex (docs/verification-sources.md).

Tried in order, each switchable via VERIFICATION_SOURCES:

1. faculty_page: an ORCID or DBLP id linked next to the name on the
   school's pages is identity proof; an ORCID iD resolves through
   OpenAlex's author filter, a DBLP id through DBLP.
2. OpenAlex (find_openalex_author).
3. dblp, computing fields only: affiliation must be the school; titles only.
4. nih, then nsf, US schools only: a PI at the school; award texts.
5. orcid: a record whose institutions include the school; titles only.

Sources 3-5 run only when OpenAlex has nobody at the school or is down,
so the common case costs nothing. Candidates get prefixed ids
("dblp:<pid>", "nih:<profile id>", "nsf:<name>@<awardee>", "orcid:<iD>")
and their works are recorded for grounding at once. A failing source is
skipped, never raised: an outage can't fail a task.
"""

from __future__ import annotations

import logging
import re

import httpx

from api.core.config import settings
from api.core.textnorm import normalize_text
from api.prospects import (
    dblp,
    grants,
    grounding,
    openalex,
    orcid,
    profile_ids,
    semantic_scholar,
)
from api.prospects.source_http import SourceUnavailable

log = logging.getLogger(__name__)

KNOWN = ("faculty_page", "dblp", "nih", "nsf", "orcid", "semantic_scholar")
#: "orcid" is an OpenAlex author proven by a faculty-page ORCID iD;
#: "orcid_record" is a professor verified from their ORCID record alone.
LABELS = {
    "orcid": "ORCID",
    "orcid_record": "ORCID",
    "dblp": "DBLP",
    "nih": "NIH RePORTER",
    "nsf": "NSF awards",
}

#: Fields DBLP covers: computer science and its neighbours.
_COMPUTING = re.compile(
    r"comput|informatic|software|artificial intelligence|machine learning|deep learning|"
    r"data science|data mining|robotic|cyber|cryptograph|information (science|systems|technology)|"
    r"human.computer|\bhci\b|\beecs\b|\bcse\b|\bcs\b|electrical (and|&) computer|"
    r"natural language|\bnlp\b|computer vision|algorithm|database|distributed systems|"
    r"programming|networking|\bai\b",
    re.IGNORECASE,
)
_US = {"united states", "united states of america", "usa", "us", "u s", "u s a", "america"}
#: Words dropped before comparing institution names word by word.
_FILLER = {"the", "at", "in"}
_INSTITUTION_HINT = re.compile(
    r"univ|institut|college|school|polytechn|academy|ecole|hochschule|centre|center|laborator",
    re.IGNORECASE,
)


def chain() -> list[str]:
    names = [n.strip().lower() for n in settings.verification_sources.split(",") if n.strip()]
    return [n for n in dict.fromkeys(names) if n in KNOWN]


def enabled(name: str) -> bool:
    return name in chain()


def stands_in_for_openalex() -> bool:
    """Can another source verify a professor while OpenAlex is down?"""
    return any(n in chain() for n in ("dblp", "nih", "nsf", "orcid"))


def is_computing(*texts: str | None) -> bool:
    return any(_COMPUTING.search(t) for t in texts if t)


def us_school(school) -> bool:
    country = normalize_text(getattr(school, "country", None))
    return not country or country in _US


def name_matches(wanted: str, other: str | None) -> bool:
    """The faculty name's first and last names are both in `other`."""
    first, last = split_name(wanted)
    tokens = set(normalize_text(other).split())
    return bool(first and last) and {normalize_text(first), normalize_text(last)} <= tokens


def split_name(name: str) -> tuple[str, str]:
    """(first, last), "Smith, Jane" included."""
    cleaned = openalex.clean_person_name(name) or name
    if cleaned.count(",") == 1:
        family, given = (p.strip() for p in cleaned.split(","))
        cleaned = f"{given} {family}"
    parts = [p for p in cleaned.replace(",", " ").split() if len(p.strip(".")) > 1]
    return (parts[0], parts[-1]) if len(parts) >= 2 else ("", "")


def _words(text: str | None) -> str:
    raw = re.sub(r"\buniv\b\.?", "university", (text or "").replace("&", " and "), flags=re.IGNORECASE)
    return " ".join(w for w in normalize_text(raw).split() if w not in _FILLER)


def institution_match(affiliations: list[str], school_all: list[str]) -> bool:
    """The school's whole name (or acronym) must appear, in order, in an
    affiliation or one of its comma-separated parts, so "University of
    Michigan" is not "Michigan State University"."""
    for affiliation in affiliations:
        segments = [s.strip() for s in re.split(r"[,;]", affiliation) if s.strip()]
        parts = [affiliation, *[s for s in segments if _INSTITUTION_HINT.search(s)], *segments[:1]]
        for part in parts:
            have = f" {_words(part)} "
            for school in school_all:
                if grounding._strong_name_match(part, school):
                    return True
                want = _words(school)
                if want and f" {want} " in have:
                    return True
    return False


def _school_all(school, school_names) -> list[str]:
    return [n for n in [getattr(school, "name", None), *(school_names or [])] if n]


def _candidate(prefix: str, source_id: str, **fields) -> dict:
    return {
        "openalex_id": f"{prefix}:{source_id}",
        "source": prefix,
        "source_id": source_id,
        **fields,
    }


_DOI = re.compile(r"\b(10\.\d{4,9}/\S+)", re.IGNORECASE)


def _doi(work: dict) -> str | None:
    if work.get("doi"):
        return str(work["doi"]).lower()
    found = _DOI.search(str(work.get("url") or ""))
    return found.group(1).rstrip(".").lower() if found else None


async def with_abstracts(works: list[dict]) -> int:
    """Fill abstracts by DOI in place; returns how many works have one. Never raises."""
    if enabled("semantic_scholar"):
        by_doi = {d: w for w in works if not w.get("abstract") and (d := _doi(w))}
        found = await _safe("semantic_scholar", semantic_scholar.abstracts(list(by_doi))) or {}
        for doi, abstract in found.items():
            if doi in by_doi:
                by_doi[doi]["abstract"] = abstract
    return sum(1 for w in works if w.get("abstract"))


def _scored_on(works: list[dict], with_abstract: int) -> tuple[str, str]:
    """(confidence, how it was scored) for works from a titles-only source."""
    if with_abstract:
        return (
            f"lower: abstracts for {with_abstract} of {len(works)} works, titles for the rest",
            f"scored on {with_abstract} abstracts and {len(works) - with_abstract} titles, so lower confidence",
        )
    return "lower: publication titles only, no abstracts", "scored on publication titles only, so lower confidence"


async def _dblp_candidate(record: dict, verified_by: str, links: list[dict]) -> dict | None:
    works = dblp.recent_works(record)
    if not works:
        return None
    confidence, scored = _scored_on(works, await with_abstracts(works))
    url = f"https://dblp.org/pid/{record['pid']}"
    how = "the DBLP profile linked on their faculty page" if verified_by == "faculty_page" else "DBLP"
    return _candidate(
        "dblp",
        record["pid"],
        display_name=record["name"],
        institution=(record["affiliations"] or [None])[0],
        institutions=record["affiliations"],
        verified_by=verified_by,
        works_count=record["count"],
        confidence=confidence,
        links=_merge_links([{"label": "DBLP", "url": url}], links),
        save_note=f"Verified via {how}; {scored}.",
        works=works,
    )


async def _orcid_candidate(
    orcid_id: str, name: str, institutions: list[str], verified_by: str, links: list[dict]
) -> dict | None:
    all_works = await _safe("orcid", orcid.works(orcid_id))
    works = orcid.recent_works(all_works or [])
    if not works:
        return None
    confidence, scored = _scored_on(works, await with_abstracts(works))
    how = "the ORCID iD linked on their faculty page" if verified_by == "faculty_page" else "their ORCID record"
    return _candidate(
        "orcid",
        orcid_id,
        source="orcid_record",
        display_name=name,
        institution=(institutions or [None])[0],
        institutions=institutions,
        verified_by=verified_by,
        works_count=len(all_works or []),
        confidence=confidence,
        orcid=orcid_id,
        links=_merge_links([{"label": "ORCID", "url": f"https://orcid.org/{orcid_id}"}], links),
        save_note=f"Verified via {how}; {scored}.",
        works=works,
    )


def _merge_links(*groups: list[dict]) -> list[dict]:
    seen, out = set(), []
    for group in groups:
        for link in group:
            if link["url"] not in seen:
                seen.add(link["url"])
                out.append(link)
    return out


async def _safe(source: str, call):
    """A source's answer, or None when it failed (logged, never raised)."""
    try:
        return await call
    except (SourceUnavailable, httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        log.info("%s lookup skipped: %s", source, exc)
        return None


async def faculty_page_candidates(ctx, school, name: str) -> list[dict]:
    """A candidate proven by an id linked on the school's pages, or []."""
    if not enabled("faculty_page"):
        return []
    program = getattr(ctx, "program", None)
    pages = [getattr(program, "department_url", None), getattr(school, "website_url", None)]
    found = profile_ids.lookup(name, pages)
    if not found:
        return []
    links = profile_ids.links(found)
    orcid_id = found.get("orcid")
    if orcid_id and openalex.down_until() is None:
        try:
            matches = [
                c for c in await openalex.find_author_by_orcid(orcid_id) if name_matches(name, c["display_name"])
            ]
        except (openalex.OpenAlexUnavailable, httpx.HTTPError):
            matches = []
        if len(matches) == 1:
            return [
                {
                    **matches[0],
                    "source": "orcid",
                    "verified_by": "faculty_page",
                    "orcid": orcid_id,
                    "links": links,
                    "save_note": "Identity from the ORCID iD linked on their faculty page.",
                }
            ]
    if orcid_id and enabled("orcid") and openalex.down_until() is not None:
        # OpenAlex can't resolve the iD, but the school's link still proves identity.
        record_name = await _safe("orcid", orcid.person_name(orcid_id))
        if record_name and name_matches(name, record_name):
            candidate = await _orcid_candidate(orcid_id, record_name, [], "faculty_page", links)
            if candidate is not None:
                return [candidate]
    pid = found.get("dblp")
    if pid and enabled("dblp"):
        record = await _safe("dblp", dblp.person(pid))
        if record and name_matches(name, record["name"]):
            candidate = await _dblp_candidate(record, "faculty_page", links)
            if candidate is not None:
                return [candidate]
    return []


async def _dblp_lookup(name: str, school_all: list[str]) -> list[dict]:
    hits = [h for h in await dblp.search_authors(name) if name_matches(name, h["name"])]
    out = []
    for hit in hits[:3]:
        if hit["affiliations"] and not institution_match(hit["affiliations"], school_all):
            continue
        record = await _safe("dblp", dblp.person(hit["pid"]))
        if not record or not institution_match(record["affiliations"] or hit["affiliations"], school_all):
            continue
        candidate = await _dblp_candidate(record, "affiliation", [])
        if candidate is not None:
            out.append(candidate)
    return out


async def _orcid_lookup(name: str, school_all: list[str]) -> list[dict]:
    given, family = split_name(name)
    people = await orcid.search_people(given, family)
    out = []
    for person in people:
        named = any(name_matches(name, n) for n in [person["name"], *person["other_names"]])
        if not named or not institution_match(person["institutions"], school_all):
            continue
        candidate = await _orcid_candidate(person["orcid"], person["name"], person["institutions"], "affiliation", [])
        if candidate is not None:
            out.append(candidate)
        if len(out) >= 3:
            break
    return out


def _grant_candidates(source: str, awards: list[dict], name: str, school_all: list[str]) -> list[dict]:
    by_pi: dict[str, list[dict]] = {}
    for award in awards:
        if name_matches(name, award["pi_name"]) and institution_match(
            [award["institution"] or ""], school_all
        ):
            by_pi.setdefault(award["pi_id"], []).append(award)
    label = LABELS[source]
    out = []
    for pi_id, mine in by_pi.items():
        works = [a["work"] for a in mine][: grants.MAX_AWARDS]
        institution = mine[0]["institution"]
        active = [w for w in works if w["active"]]
        out.append(
            _candidate(
                source,
                pi_id,
                display_name=" ".join(w.capitalize() for w in mine[0]["pi_name"].split()),
                institution=institution,
                institutions=[institution],
                verified_by="affiliation",
                works_count=len(works),
                confidence="medium: scored on grant abstracts, not papers",
                active_grants=[_grant_brief(w) for w in active][:3],
                links=[{"label": label, "url": works[0]["url"]}],
                save_note=(
                    f"Verified via {label}: principal investigator at {institution}; "
                    "scored on grant abstracts, not papers."
                ),
                works=works,
            )
        )
    return out


def _grant_brief(work: dict) -> dict:
    return {"title": work["title"], "ends": work["ends"], "url": work["url"]}


async def _nih_lookup(name: str, school_all: list[str]) -> list[dict]:
    first, last = split_name(name)
    return _grant_candidates("nih", await grants.nih_awards(first, last), name, school_all)


async def _nsf_lookup(name: str, school_all: list[str]) -> list[dict]:
    first, last = split_name(name)
    return _grant_candidates("nsf", await grants.nsf_awards(first, last), name, school_all)


_LOOKUPS = {"dblp": _dblp_lookup, "nih": _nih_lookup, "nsf": _nsf_lookup, "orcid": _orcid_lookup}


def _applies(source: str, ctx, school) -> bool:
    if source == "orcid":
        return True
    if source == "dblp":
        run, program = getattr(ctx, "run", None), getattr(ctx, "program", None)
        return is_computing(getattr(run, "field", None), getattr(program, "name", None))
    return us_school(school)


async def fallback_candidates(ctx, school, name: str, school_names=()) -> list[dict]:
    """Candidates from the first applicable source after OpenAlex that has any."""
    if not split_name(name)[0]:
        return []
    school_all = _school_all(school, school_names)
    if not school_all:
        return []
    for source in chain():
        lookup = _LOOKUPS.get(source)
        if lookup is None or not _applies(source, ctx, school):
            continue
        found = await _safe(source, lookup(name, school_all))
        if found:
            return found
    return []


async def active_grants(ctx, school, name: str, school_names=()) -> list[dict]:
    """Running NIH/NSF awards for this PI at the school: a sign the lab can fund a student."""
    if not us_school(school) or not split_name(name)[0]:
        return []
    school_all = _school_all(school, school_names)
    out: list[dict] = []
    for source in ("nih", "nsf"):
        if not enabled(source) or not school_all:
            continue
        found = await _safe(source, _LOOKUPS[source](name, school_all)) or []
        if len(found) == 1:
            out += [{**g, "source": LABELS[source]} for g in found[0]["active_grants"]]
    return out[:3]


def record(ctx, candidates: list[dict]) -> list[dict]:
    """Record candidates for grounding; returns them as the model reads them (works counted)."""
    shown = []
    for candidate in candidates:
        works = candidate.pop("works", None)
        if works is not None:
            grounding.record_works(ctx, candidate["openalex_id"], works)
        shown.append(candidate)
    grounding.record_author_candidates(ctx, shown)
    return [
        {k: v for k, v in c.items() if k not in ("save_note", "links")}
        for c in shown
    ]


#: What the model is told about candidates from another source.
SOURCE_NOTE = (
    "Candidates with a `source` come from {sources}, not OpenAlex: their works are "
    "already fetched, so call score_alignment with that openalex_id (dblp:, nih:, nsf: or "
    "orcid: id) and save with it the same way."
)


def note_for(candidates: list[dict]) -> str | None:
    labels = sorted({LABELS.get(c.get("source", ""), "") for c in candidates if c.get("source")} - {""})
    if not labels or all(c.get("source") == "orcid" for c in candidates if c.get("source")):
        return None
    return SOURCE_NOTE.format(sources=", ".join(labels))
