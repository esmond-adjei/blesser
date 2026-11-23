import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import trafilatura
from lxml import html as lxml_html

from api.applications.dates import parse_deadline

_DATE = re.compile(
    r"\b(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?[A-Za-z]{3,9}\.?[,]?\s+\d{4}|[A-Za-z]{3,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?[,]?\s+\d{4})(?!\d)",
    re.IGNORECASE,
)
_DEADLINE = re.compile(
    r"\b(?:application\s+deadline|deadline|closing\s+date|apply\s+by|applications?\s+close(?:s)?|submission\s+deadline)\b",
    re.IGNORECASE,
)
_ROLLING = re.compile(
    r"\b(?:rolling\s+(?:admissions|applications|basis|deadline)|applications?\s+(?:are\s+)?(?:always\s+open|accepted\s+year.round)|apply\s+anytime)\b",
    re.IGNORECASE,
)


def normalized_url(url: str) -> str:
    try:
        p = urlsplit(url.strip())
        pairs = sorted(
            (k, v)
            for k, v in parse_qsl(p.query, keep_blank_values=True)
            if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}
        )
        return urlunsplit(
            (
                "https",
                p.netloc.lower().removeprefix("www."),
                p.path.rstrip("/") or "/",
                urlencode(pairs),
                "",
            )
        )
    except ValueError:
        return url.strip()


def dates_in(text: str) -> list[date]:
    return sorted(
        {
            d
            for m in _DATE.finditer(text)
            if (d := parse_deadline(m.group())) is not None
        }
    )


def deadline_dates(text: str, metadata: dict | None = None) -> list[date]:
    values = []
    for match in _DEADLINE.finditer(text):
        following = text[match.end() : match.end() + 110].split("\n\n", 1)[0]
        if dates := dates_in(following):
            values.extend(dates)
    for raw in (metadata or {}).get("deadlines", []):
        if d := parse_deadline(str(raw)[:10]):
            values.append(d)
    return sorted(set(values))


def expired(text: str, metadata: dict, today: date) -> bool:
    deadlines = deadline_dates(text, metadata)
    return bool(deadlines) and max(deadlines) < today and not _ROLLING.search(text)


def confirms_deadline(
    text: str, metadata: dict, deadline: date | None, rolling: bool, today: date
) -> bool:
    """The page still states this listing's deadline as its latest, or still says rolling."""
    if rolling:
        return bool(_ROLLING.search(text)) and not expired(text, metadata, today)
    if deadline is None or deadline < today:
        return False
    deadlines = deadline_dates(text, metadata)
    return bool(deadlines) and max(deadlines) == deadline


def shows_open_cycle(text: str, metadata: dict, today: date) -> bool:
    """The page states a deadline still ahead, or says applications are rolling."""
    return any(d >= today for d in deadline_dates(text, metadata)) or bool(
        _ROLLING.search(text)
    )


@dataclass
class Page:
    url: str
    text: str = ""
    title: str = ""
    metadata: dict = field(default_factory=dict)
    content_hash: str = ""
    error: str = ""
    cached: bool = False


#: Links to other sites kept per page, for following aggregator posts (official.py).
MAX_OUTBOUND = 60


def outbound_links(tree, url: str) -> list[dict]:
    """Links in the page body to other hosts, with their labels, in page order."""
    own = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    links: dict[str, dict] = {}
    for node in tree.xpath("//body//a[@href]"):
        try:
            href = urljoin(url, node.get("href", "").strip())
            parts = urlsplit(href)
        except ValueError:
            continue
        host = (parts.hostname or "").lower().removeprefix("www.")
        if parts.scheme not in {"http", "https"} or not host or host == own:
            continue
        label = " ".join(
            (
                node.text_content() or node.get("title") or node.get("aria-label") or ""
            ).split()
        )[:200]
        key = normalized_url(href)
        if key in links:
            if label and not links[key]["label"]:
                links[key]["label"] = label
            continue
        links[key] = {"url": href[:2000], "label": label}
        if len(links) >= MAX_OUTBOUND:
            break
    return list(links.values())


def parse_page(raw: str, url: str) -> Page:
    tree = lxml_html.fromstring(raw)
    title = " ".join(
        tree.xpath("//head/title/text()") or tree.xpath("//title/text()")[:1]
    )[:300]
    metadata: dict = {"deadlines": [], "structured": []}
    for node in tree.xpath('//script[@type="application/ld+json"]')[:12]:
        try:
            value = json.loads(node.text or "")
        except (ValueError, TypeError):
            continue
        metadata["structured"].append(value)

    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.lower() in {
                    "validthrough",
                    "applicationdeadline",
                    "deadline",
                    "closingdate",
                } and isinstance(item, str):
                    metadata["deadlines"].append(item)
                if key == "datePublished" and isinstance(item, str):
                    metadata["published_date"] = item[:10]
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(metadata["structured"])
    for node in tree.xpath("//meta[@content]"):
        key = (node.get("property") or node.get("name") or "").lower()
        if key in {"application:deadline", "deadline", "validthrough"}:
            metadata["deadlines"].append(node.get("content"))
        if key in {"article:published_time", "datepublished"}:
            metadata["published_date"] = node.get("content", "")[:10]
    metadata["feeds"] = [
        urljoin(url, href)
        for href in tree.xpath(
            '//link[@rel="alternate"][contains(@type, "rss") or contains(@type, "atom")]/@href'
        )[:5]
    ]
    for node in tree.xpath("//nav|//footer|//body/header|//script|//style|//noscript"):
        node.drop_tree()
    metadata["outbound"] = outbound_links(tree, url)
    clean = lxml_html.tostring(tree, encoding="unicode")
    text = trafilatura.extract(clean, include_links=True) or tree.text_content()
    headings = "\n".join(tree.xpath("//h1//text()"))[:2000]
    text = title + "\n" + headings + "\n" + text
    structured = json.dumps(metadata["structured"], ensure_ascii=False)[:12000]
    if metadata["structured"]:
        text += "\nStructured page data:\n" + structured
    from api.opportunities.crawler import parse_items

    metadata["links"], _ = parse_items(raw, url, "listing", 40)
    for item in metadata["links"]:
        item["published_date"] = None
    text = text[:400000]
    return Page(
        url=url,
        text=text,
        title=title,
        metadata=metadata,
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
    )


def page_note(page: Page, verdict: str = "read") -> str:
    dates = (
        ",".join(d.isoformat() for d in deadline_dates(page.text, page.metadata))
        or "none stated"
    )
    return f"{page.url} | {page.title[:120]} | deadline: {dates} | {verdict}"[:600]
