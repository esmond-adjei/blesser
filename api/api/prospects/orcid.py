"""ORCID public API: expanded search and works (no abstracts).

ORCID's institution filter is a loose text match, so people are searched
by name and institutions matched strictly here.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from api.prospects import source_http

SEARCH_URL = "https://pub.orcid.org/v3.0/expanded-search/"
WORKS_URL = "https://pub.orcid.org/v3.0/{}/works"
PERSON_URL = "https://pub.orcid.org/v3.0/{}/personal-details"
HEADERS = {"Accept": "application/json"}
MAX_WORKS = 50
RECENT_YEARS = 5
SEARCH_ROWS = 10
ORCID_ID = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
#: Lucene's reserved characters, dropped from names before searching.
_RESERVED = re.compile(r'[+\-&|!(){}\[\]^"~*?:\\/]')


def _term(value: str) -> str:
    return " ".join(_RESERVED.sub(" ", value).split())


def _value(node) -> str | None:
    """ORCID wraps scalars as {"value": ...}."""
    if isinstance(node, dict):
        value = node.get("value")
        return str(value).strip() if value not in (None, "") else None
    return None


async def search_people(given: str, family: str) -> list[dict]:
    """[{"orcid", "name", "institutions"}] for a name, ORCID's order."""
    given, family = _term(given), _term(family)
    if not given or not family:
        return []
    data = await source_http.request(
        "orcid",
        SEARCH_URL,
        params={"q": f"given-names:({given}) AND family-name:({family})", "rows": SEARCH_ROWS},
        headers=HEADERS,
    )
    out = []
    for row in data.get("expanded-result") or []:
        orcid = str((row or {}).get("orcid-id") or "")
        if not ORCID_ID.match(orcid):
            continue
        name = " ".join(p for p in (row.get("given-names"), row.get("family-names")) if p)
        out.append(
            {
                "orcid": orcid,
                "name": name,
                "other_names": [str(n) for n in row.get("other-name") or [] if n],
                "institutions": [str(i) for i in row.get("institution-name") or [] if i],
            }
        )
    return out


async def person_name(orcid: str) -> str | None:
    data = await source_http.request("orcid", PERSON_URL.format(orcid), headers=HEADERS)
    name = data.get("name") or {}
    parts = [_value(name.get("given-names")), _value(name.get("family-name"))]
    return " ".join(p for p in parts if p) or None


def parse_works(data: dict) -> list[dict]:
    """One work per group (ORCID groups duplicates), newest first, OpenAlex-shaped."""
    works = []
    for group in data.get("group") or []:
        summaries = (group or {}).get("work-summary") or []
        if not summaries:
            continue
        summary = summaries[0]
        title = _value((summary.get("title") or {}).get("title"))
        if not title:
            continue
        year = _value((summary.get("publication-date") or {}).get("year"))
        ids = ((group.get("external-ids") or {}).get("external-id")) or []
        doi = next(
            (
                str(e.get("external-id-value")).strip().lower()
                for e in ids
                if (e or {}).get("external-id-type") == "doi" and e.get("external-id-value")
            ),
            None,
        )
        url = _value(summary.get("url")) or (f"https://doi.org/{doi}" if doi else None)
        works.append(
            {
                "title": " ".join(title.split()).rstrip("."),
                "abstract": None,
                "year": int(year) if year and year.isdigit() else None,
                "venue": _value(summary.get("journal-title")),
                "url": url,
                "doi": doi,
            }
        )
    works.sort(key=lambda w: w["year"] or 0, reverse=True)
    return works


async def works(orcid: str) -> list[dict]:
    data = await source_http.request("orcid", WORKS_URL.format(orcid), headers=HEADERS)
    return parse_works(data)


def recent_works(all_works: list[dict]) -> list[dict]:
    since = datetime.now(UTC).year - RECENT_YEARS
    return [w for w in all_works if (w["year"] or 0) >= since][:MAX_WORKS]
