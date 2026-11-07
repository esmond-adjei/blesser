"""DBLP author search (JSON) and person records (XML).

No abstracts, so a score from it is marked lower confidence.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from api.prospects import source_http

SEARCH_URL = "https://dblp.org/search/author/api"
PERSON_URL = "https://dblp.org/pid/{}.xml"
MAX_WORKS = 50
RECENT_YEARS = 5
#: DBLP's homonym suffix: "Jane Smith 0002".
_HOMONYM = re.compile(r"\s+\d{4}$")
_ORCID = re.compile(r"orcid\.org/(\d{4}-\d{4}-\d{4}-\d{3}[\dX])", re.IGNORECASE)


def _clean_name(name: str | None) -> str:
    return _HOMONYM.sub("", (name or "").strip())


def _listify(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


async def search_authors(name: str) -> list[dict]:
    """[{"pid", "name", "affiliations"}] for a name, best first."""
    data = await source_http.request(
        "dblp", SEARCH_URL, params={"q": name, "format": "json", "h": 10}
    )
    hits = _listify(((data.get("result") or {}).get("hits") or {}).get("hit"))
    out = []
    for hit in hits:
        info = (hit or {}).get("info") or {}
        url = str(info.get("url") or "")
        if "/pid/" not in url:
            continue
        notes = _listify((info.get("notes") or {}).get("note"))
        out.append(
            {
                "pid": url.split("/pid/", 1)[1].removesuffix(".html"),
                "name": _clean_name(info.get("author")),
                "affiliations": [
                    str(n.get("text"))
                    for n in notes
                    if isinstance(n, dict) and n.get("@type") == "affiliation" and n.get("text")
                ],
            }
        )
    return out


def parse_person(xml: str, pid: str) -> dict | None:
    """A person's record: {"pid", "name", "affiliations", "orcid",
    "count", "works"}, works newest first; None when unreadable."""
    from lxml import etree

    parser = etree.XMLParser(
        resolve_entities=False, no_network=True, load_dtd=False, recover=True
    )
    try:
        root = etree.fromstring(xml.encode("utf-8"), parser)
    except (etree.XMLSyntaxError, ValueError):
        return None
    if root is None or root.tag != "dblpperson":
        return None
    person = root.find("person")
    affiliations, orcid = [], None
    if person is not None:
        for note in person.findall("note"):
            if note.get("type") == "affiliation":
                text = " ".join("".join(note.itertext()).split())
                if text:
                    affiliations.append(text)
        for link in person.findall("url"):
            found = _ORCID.search(link.text or "")
            if found and orcid is None:
                orcid = found.group(1).upper()
    works = []
    for record in root.findall("r"):
        if not len(record):
            continue
        entry = record[0]
        title_node = entry.find("title")
        title = " ".join("".join(title_node.itertext()).split()).rstrip(".") if title_node is not None else ""
        if not title:
            continue
        year_text = (entry.findtext("year") or "").strip()
        ee = (entry.findtext("ee") or "").strip()
        works.append(
            {
                "title": title,
                "abstract": None,
                "year": int(year_text) if year_text.isdigit() else None,
                "publication_type": {"inproceedings": "conference-paper", "article": "journal-article", "phdthesis": "dissertation", "mastersthesis": "dissertation", "book": "book", "incollection": "book-chapter"}.get(entry.tag),
                "venue": (entry.findtext("journal") or entry.findtext("booktitle") or "").strip() or None,
                "url": ee or (f"https://dblp.org/rec/{entry.get('key')}" if entry.get("key") else None),
            }
        )
    works.sort(key=lambda w: w["year"] or 0, reverse=True)
    return {
        "pid": pid,
        "name": _clean_name(root.get("name")),
        "affiliations": affiliations,
        "orcid": orcid,
        "count": len(works),
        "works": works,
    }


async def person(pid: str) -> dict | None:
    data = await source_http.request("dblp", PERSON_URL.format(pid), text=True)
    return parse_person(data.get("text") or "", pid)


def recent_works(record: dict) -> list[dict]:
    since = datetime.now(UTC).year - RECENT_YEARS
    return [w for w in record["works"] if (w["year"] or 0) >= since][:MAX_WORKS]
