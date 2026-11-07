"""Researcher profile ids linked from the school's own pages.

A link the school published is the strongest identity proof. Links are
picked out of pages fetch_page already downloaded; nothing is fetched
(Google Scholar is never contacted).

A link belongs to the people named in the largest part of the page that
holds no second id of the same kind: a directory card, or on a profile
page the person its title or heading names. Callers still check the name
the id resolves to.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from api.core.textnorm import normalize_text
from api.core.ttlcache import TTLCache

#: kind -> (pattern on an href, canonical profile URL)
PATTERNS: dict[str, tuple[re.Pattern, str]] = {
    "orcid": (
        re.compile(r"orcid\.org/(\d{4}-\d{4}-\d{4}-\d{3}[\dX])\b", re.IGNORECASE),
        "https://orcid.org/{}",
    ),
    "dblp": (
        re.compile(r"dblp\.(?:org|uni-trier\.de)/pid/([a-z0-9]+/[A-Za-z0-9-]+?)(?:\.html|\.xml)?(?:[?#/]|$)"),
        "https://dblp.org/pid/{}",
    ),
    "scholar": (
        re.compile(r"scholar\.google\.[a-z.]+/citations\?(?:[^#]*?&)?user=([\w-]{12})"),
        "https://scholar.google.com/citations?user={}",
    ),
    "semantic_scholar": (
        re.compile(r"semanticscholar\.org/author/(?:[^/?#]+/)?(\d{3,})"),
        "https://www.semanticscholar.org/author/{}",
    ),
}
LABELS = {
    "orcid": "ORCID",
    "dblp": "DBLP",
    "scholar": "Google Scholar",
    "semantic_scholar": "Semantic Scholar",
}
_ANY = re.compile(r"orcid\.org|dblp\.|scholar\.google|semanticscholar\.org", re.IGNORECASE)
#: Characters of a link's surrounding text kept for name lookups.
_CONTEXT_CHARS = 40_000
_PER_SITE = 400
#: A context with this share of the page's words is the whole page.
_WHOLE_PAGE = 0.6

# site -> [{"kind", "id", "page", "words", "size"}]
_SEEN: TTLCache[list[dict]] = TTLCache(2000, lambda: 86400.0)


def _site(url: str | None) -> str:
    from api.prospects.web import _site as registrable

    host = urlparse(url).netloc if url else ""
    return registrable(host) if host else ""


def _match(href: str) -> tuple[str, str] | None:
    for kind, (pattern, _) in PATTERNS.items():
        found = pattern.search(href)
        if found:
            value = found.group(1)
            return kind, value.upper() if kind == "orcid" else value
    return None


def profile_url(kind: str, value: str) -> str:
    return PATTERNS[kind][1].format(value)


def remember(html: str, base_url: str) -> None:
    """Called from web._extract, off the event loop."""
    site = _site(base_url)
    if not site or not html or not _ANY.search(html):
        return
    from lxml import html as lxml_html

    try:
        doc = lxml_html.fromstring(html)
    except (ValueError, TypeError, lxml_html.etree.ParserError):
        return
    links: list[tuple[object, str, str]] = []
    for anchor in doc.iter("a"):
        hit = _match(anchor.get("href") or "")
        if hit:
            links.append((anchor, *hit))
    if not links:
        return
    # Keyed by path: lxml element proxies don't keep a stable id(). A
    # link's context stops below the first element holding two ids of a kind.
    tree = doc.getroottree()
    under: dict[str, dict[str, set[str]]] = {}
    for anchor, kind, value in links:
        for node in anchor.iterancestors():
            under.setdefault(tree.getpath(node), {}).setdefault(kind, set()).add(value)
    # A whole-page context belongs only to the person in the title or heading.
    page_size = len(_words(doc))
    heading_words = frozenset().union(*(_words(n) for n in [*doc.iter("title"), *doc.iter("h1")][:3]))
    entries = [e for e in _SEEN.get(site) or [] if e["page"] != base_url]
    for anchor, kind, value in links:
        context = anchor
        for node in anchor.iterancestors():
            if any(len(ids) > 1 for ids in under[tree.getpath(node)].values()):
                break
            context = node
        words = _words(context)
        if words:
            entries.append(
                {
                    "kind": kind,
                    "id": value,
                    "page": base_url,
                    "words": words,
                    "size": len(words),
                    "whole_page": len(words) >= _WHOLE_PAGE * page_size,
                    "heading": heading_words,
                }
            )
    _SEEN.put(site, entries[-_PER_SITE:])


def _words(node) -> frozenset[str]:
    """The element's words; text of adjacent elements kept apart."""
    text = " ".join(node.itertext())[:_CONTEXT_CHARS]
    return frozenset(normalize_text(text).split())


def _name_tokens(name: str) -> set[str]:
    from api.prospects.openalex import clean_person_name

    tokens = [t for t in normalize_text(clean_person_name(name) or name).split() if len(t) > 1]
    return {tokens[0], tokens[-1]} if len(tokens) >= 2 else set()


def lookup(name: str, page_urls: list[str | None]) -> dict[str, str]:
    """{kind: id} linked next to `name`; a kind whose most specific matches disagree is left out."""
    wanted = _name_tokens(name)
    if not wanted:
        return {}
    best: dict[str, tuple[int, set[str]]] = {}
    for site in dict.fromkeys(_site(u) for u in page_urls if u):
        for entry in _SEEN.get(site) or []:
            if not wanted <= entry["words"]:
                continue
            if entry["whole_page"] and not wanted <= entry["heading"]:
                continue
            size, ids = best.get(entry["kind"], (entry["size"] + 1, set()))
            if entry["size"] < size:
                best[entry["kind"]] = (entry["size"], {entry["id"]})
            elif entry["size"] == size:
                ids.add(entry["id"])
    return {kind: next(iter(ids)) for kind, (_, ids) in best.items() if len(ids) == 1}


def links(found: dict[str, str]) -> list[dict]:
    return [{"label": LABELS[k], "url": profile_url(k, v)} for k, v in found.items() if k in LABELS]
