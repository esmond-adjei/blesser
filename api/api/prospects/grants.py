"""US research grants as evidence: NIH RePORTER and NSF awards (keyless).

NIH asks for at most one request a second. A PI at the programme's school
verifies the professor; award texts are scored; a running award is a
funding signal.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

from api.core.textnorm import normalize_text
from api.prospects import source_http

NIH_URL = "https://api.reporter.nih.gov/v2/projects/search"
NSF_URL = "https://api.nsf.gov/services/v1/awards.json"
#: Awards this many fiscal years back still describe current research.
GRANT_YEARS = 6
MAX_AWARDS = 50
#: NSF's awards API returns at most 25 records per page.
NSF_PAGE = 25
_NSF_FIELDS = "id,title,abstractText,awardeeName,piFirstName,piLastName,startDate,expDate"
#: "5R01GM123456-04" -> "R01GM123456": one project across its years.
_CORE = re.compile(r"^\d?([A-Z]\d{2}[A-Z]{2}\d{6})", re.IGNORECASE)


def _today() -> date:
    return datetime.now(UTC).date()


def _iso(value: str | None) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _us(value: str | None) -> date | None:
    """NSF's "MM/DD/YYYY"."""
    if not value:
        return None
    try:
        month, day, year = (int(p) for p in str(value).split("/"))
        return date(year, month, day)
    except ValueError:
        return None


def _work(title: str, abstract: str | None, start: date | None, end: date | None, url: str, label: str) -> dict:
    return {
        "title": f"{title.strip()} [{label}]",
        "abstract": (abstract or "").strip() or None,
        "year": start.year if start else None,
        "venue": label.split(" ", 1)[0],
        "url": url,
        "ends": end.isoformat() if end else None,
        "active": bool(end and end >= _today()),
    }


async def nih_awards(first: str, last: str) -> list[dict]:
    """[{"pi_id", "pi_name", "institution", "work"}] for recent fiscal years."""
    this_year = _today().year
    data = await source_http.request(
        "nih",
        NIH_URL,
        body={
            "criteria": {
                "pi_names": [{"first_name": first, "last_name": last}],
                "fiscal_years": list(range(this_year - GRANT_YEARS, this_year + 1)),
            },
            "offset": 0,
            "limit": MAX_AWARDS,
            "sort_field": "project_start_date",
            "sort_order": "desc",
        },
    )
    out, seen = [], set()
    for project in data.get("results") or []:
        if not isinstance(project, dict) or not project.get("project_title"):
            continue
        number = str(project.get("project_num") or "")
        core = _CORE.match(number)
        dedup = (core.group(1).upper() if core else number) or normalize_text(project["project_title"])
        for pi in project.get("principal_investigators") or []:
            if not isinstance(pi, dict) or not pi.get("profile_id"):
                continue
            if (pi["profile_id"], dedup) in seen:
                continue
            seen.add((pi["profile_id"], dedup))
            url = project.get("project_detail_url") or (
                f"https://reporter.nih.gov/project-details/{project.get('appl_id')}"
            )
            out.append(
                {
                    "pi_id": str(pi["profile_id"]),
                    "pi_name": pi.get("full_name")
                    or f"{pi.get('first_name') or ''} {pi.get('last_name') or ''}".strip(),
                    "institution": (project.get("organization") or {}).get("org_name"),
                    "work": _work(
                        project["project_title"],
                        project.get("abstract_text"),
                        _iso(project.get("project_start_date")),
                        _iso(project.get("project_end_date")),
                        url,
                        f"NIH grant {core.group(1).upper() if core else number}".strip(),
                    ),
                }
            )
    return out


async def nsf_awards(first: str, last: str) -> list[dict]:
    """Same shape as nih_awards; NSF has no PI id, so name and awardee stand in."""
    data = await source_http.request(
        "nsf",
        NSF_URL,
        params={"pdPIName": f"{first} {last}", "printFields": _NSF_FIELDS, "rpp": NSF_PAGE},
    )
    since = _today().year - GRANT_YEARS
    out = []
    for award in (data.get("response") or {}).get("award") or []:
        if not isinstance(award, dict) or not award.get("title") or not award.get("id"):
            continue
        end = _us(award.get("expDate"))
        if end is not None and end.year < since:
            continue
        name = f"{award.get('piFirstName') or ''} {award.get('piLastName') or ''}".strip()
        institution = award.get("awardeeName")
        out.append(
            {
                "pi_id": "-".join(normalize_text(name).split())
                + "@"
                + "-".join(normalize_text(institution).split()),
                "pi_name": name,
                "institution": institution,
                "work": _work(
                    award["title"],
                    award.get("abstractText"),
                    _us(award.get("startDate")),
                    end,
                    f"https://www.nsf.gov/awardsearch/showAward?AWD_ID={award['id']}",
                    f"NSF award {award['id']}",
                ),
            }
        )
    return out
