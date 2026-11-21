"""Official pages for finds on aggregator sites.

Aggregators (opportunity blogs and listing sites) repost calls that funders publish on
their own sites. Members should apply on the funder's page, so a find on an aggregator
is followed to the official page before it is stored:

1. The aggregator post's outbound links are ranked: the extracted application link
   first, then links labelled "apply", "official website" and the like, then links
   whose host carries the organization's name. Social, sharing and other aggregator
   hosts are skipped.
2. Up to `MAX_TRIES` of them are read through the shared page cache. The first page
   that names the opportunity by its title (an organization's name alone is not
   enough) and is not itself on an aggregator after redirects is the official page.
3. When the aggregator stated a deadline, the official page decides it: the same date
   is kept; a single different date on the official page replaces it; otherwise the
   deadline is cleared and the listing is held for review.

The aggregator URL is kept in `opportunities.found_via_url` for staff only.
"""

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from api.applications.dates import parse_deadline
from api.opportunities.page_content import (
    Page,
    dates_in,
    deadline_dates,
    normalized_url,
)
from api.opportunities.triage import is_social_host

#: Official-page candidates read per aggregator post.
MAX_TRIES = 3

#: Seeded list of aggregator sites; staff edit it in admin settings.
DEFAULT_AGGREGATORS = (
    "opportunitydesk.org",
    "opportunitiesforafricans.com",
    "opportunitiescorners.com",
    "opportunitiescorners.info",
    "afterschoolafrica.com",
    "scholarshipregion.com",
    "youthop.com",
    "opportunitiesforyouth.org",
    "scholars4dev.com",
    "scholarshipsads.com",
    "scholarship-positions.com",
    "scholarshiproar.com",
    "fundsforngos.org",
    "advance-africa.com",
    "mladiinfo.eu",
    "opportunitytracker.ug",
    "studentsdiscount.ng",
    "myschoolgist.com",
)

#: Hosts that never hold an opportunity's official page.
_NEVER_OFFICIAL = frozenset(
    {
        "wa.me",
        "whatsapp.com",
        "t.me",
        "telegram.me",
        "telegram.org",
        "pinterest.com",
        "reddit.com",
        "tumblr.com",
        "tiktok.com",
        "threads.net",
        "wikipedia.org",
        "gravatar.com",
        "wordpress.com",
        "wordpress.org",
        "feedburner.com",
        "amazon.com",
        "play.google.com",
        "apps.apple.com",
        "googleads.g.doubleclick.net",
        "doubleclick.net",
    }
)

_STRONG = re.compile(
    r"\b(?:apply|application|applications|submit|portal|register|registration|nominate)\b"
)
_WEAK = re.compile(
    r"\b(?:official|website|site|visit|more\s+info(?:rmation)?|learn\s+more|details|"
    r"guidelines|call\s+document|announcement|here)\b"
)
_PATH_HINT = re.compile(
    r"(?:apply|application|scholarship|grant|fellowship|call|award|programme|program|"
    r"opportunit|competition|internship|admission)"
)


def host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def clean_hosts(values) -> list[str]:
    """Bare lowercase hosts from staff input: URLs and `www.` are trimmed."""
    hosts = []
    for value in values or []:
        text = str(value).strip().lower()
        if not text:
            continue
        host = host_of(text if "://" in text else "https://" + text)
        if host and "." in host and host not in hosts:
            hosts.append(host)
    return hosts


def on_hosts(url: str, hosts) -> bool:
    host = host_of(url)
    return bool(host) and any(host == h or host.endswith("." + h) for h in hosts)


async def aggregator_hosts(session) -> frozenset[str]:
    from api.editorial.service import get_settings

    values = (await get_settings(session)).get("aggregators")
    return frozenset(clean_hosts(DEFAULT_AGGREGATORS if values is None else values))


def is_aggregator(url: str, hosts) -> bool:
    return on_hosts(url, hosts)


def _org_words(organization: str) -> list[str]:
    from api.opportunities.service import normalize

    return [w for w in normalize(organization).split() if len(w) >= 4]


def ranked_links(
    page: Page, *, hosts, organization: str = "", preferred: str = ""
) -> list[str]:
    """Outbound links of an aggregator post that may be the official page, best first."""
    own = host_of(page.url)
    org_words = _org_words(organization)
    scored: dict[str, tuple[int, int]] = {}
    links = list(page.metadata.get("outbound") or [])
    if preferred:
        links.insert(0, {"url": preferred, "label": "", "preferred": True})
    for index, item in enumerate(links):
        url = str(item.get("url", ""))
        host = host_of(url)
        if (
            not host
            or urlsplit(url).scheme not in {"http", "https"}
            or host == own
            or on_hosts(url, hosts)
            or on_hosts(url, _NEVER_OFFICIAL)
            or is_social_host(url)
            or urlsplit(url)
            .path.lower()
            .endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".zip", ".mp4"))
        ):
            continue
        label = " ".join(str(item.get("label", "")).lower().split())
        score = 0
        if item.get("preferred"):
            score += 10
        if _STRONG.search(label):
            score += 4
        elif _WEAK.search(label):
            score += 2
        if _PATH_HINT.search(urlsplit(url).path.lower()):
            score += 1
        compact_host = host.replace("-", "")
        if any(word in compact_host for word in org_words):
            score += 3
        if score <= 0:
            continue
        key = normalized_url(url)
        best = scored.get(key)
        if best is None or score > best[0]:
            scored[key] = (score, -index if best is None else best[1])
    order = sorted(scored.items(), key=lambda kv: (-kv[1][0], -kv[1][1]))
    return [url for url, _ in order]


@dataclass
class Resolution:
    """The official page found for an aggregator post, or why none was."""

    page: Page | None = None
    deadline: str | None = None
    deadline_changed: bool = False
    deadline_unclear: bool = False
    tried: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        if self.page is None:
            return ""
        return str(self.page.metadata.get("final_url") or self.page.url)


def settle_deadline(stated: str, official: Page) -> tuple[str, bool, bool]:
    """(deadline, changed, unclear) once the official page is read.

    The official page decides: the aggregator's date is kept when the page shows it, a
    single deadline on the page replaces it, and anything else clears it for review."""
    stated_date = parse_deadline(stated) if stated.strip() else None
    dates = deadline_dates(official.text, official.metadata)
    if stated_date is None:
        if len(dates) == 1:
            return dates[0].isoformat(), True, False
        return stated, False, False
    if stated_date in dates_in(official.text):
        return stated, False, False
    if len(dates) == 1:
        return dates[0].isoformat(), True, False
    return "", True, True


def names_title(text: str, title: str, organization: str) -> bool:
    """The page names this opportunity, not only its organization.

    Aggregator titles carry extra words ("fully funded", the host country), so half of
    the title's distinctive words are enough, or a third when the organization is
    named too. An organization's name alone is not enough: every page on its site
    has it."""
    from api.opportunities.service import normalize
    from api.opportunities.tools import _words

    haystack = f" {normalize(text)} "
    words = _words(title)
    if not words:
        return False
    share = sum(1 for w in words if f" {w} " in haystack) / len(words)
    org = normalize(organization)
    return share >= 0.5 or (share >= 0.34 and bool(org) and f" {org} " in haystack)


async def resolve_official(
    page: Page,
    *,
    title: str,
    organization: str,
    deadline: str = "",
    preferred_link: str = "",
    hosts,
    fetch=None,
) -> Resolution:
    """Follow an aggregator post to the opportunity's own page."""
    if fetch is None:
        from api.opportunities.page_cache import get_page as fetch
    result = Resolution()
    for url in ranked_links(
        page, hosts=hosts, organization=organization, preferred=preferred_link
    )[:MAX_TRIES]:
        result.tried.append(url)
        official = await fetch(url)
        if official.error or len(official.text.strip()) < 80:
            continue
        final = str(official.metadata.get("final_url") or official.url)
        if is_aggregator(final, hosts) or is_social_host(final):
            continue
        if not names_title(official.text, title, organization):
            continue
        result.page = official
        (
            result.deadline,
            result.deadline_changed,
            result.deadline_unclear,
        ) = settle_deadline(deadline, official)
        return result
    return result
