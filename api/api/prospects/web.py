"""search_web and fetch_page: the least reliable stages, so the agent is
prompted to cross-check what they return."""

import asyncio
import re

import httpx
import trafilatura

from api.core import egress
from api.core.config import settings
from api.core.ttlcache import TTLCache

# Process-wide, built lazily: a Semaphore binds to the loop that first awaits it.
_SEARCH_SEM: asyncio.Semaphore | None = None
_FETCH_SEM: asyncio.Semaphore | None = None

# Shared clients reuse connections instead of a TLS handshake per tool call.
_search_client: httpx.AsyncClient | None = None
_fetch_client: httpx.AsyncClient | None = None


def _sem(current: asyncio.Semaphore | None, size: int) -> asyncio.Semaphore:
    return current if current is not None else asyncio.Semaphore(max(1, size))


def _search_sem() -> asyncio.Semaphore:
    global _SEARCH_SEM
    _SEARCH_SEM = _sem(_SEARCH_SEM, settings.http_search_concurrency)
    return _SEARCH_SEM


def _fetch_sem() -> asyncio.Semaphore:
    global _FETCH_SEM
    _FETCH_SEM = _sem(_FETCH_SEM, settings.http_fetch_concurrency)
    return _FETCH_SEM


def search_client() -> httpx.AsyncClient:
    global _search_client
    if _search_client is None or _search_client.is_closed:
        _search_client = httpx.AsyncClient(
            timeout=20,
            limits=httpx.Limits(
                max_connections=max(1, settings.http_search_concurrency),
                keepalive_expiry=60.0,
            ),
        )
    return _search_client


def fetch_client() -> httpx.AsyncClient:
    global _fetch_client
    if _fetch_client is None or _fetch_client.is_closed:
        _fetch_client = httpx.AsyncClient(
            timeout=20,
            # egress.safe_get follows redirects, re-checking each hop.
            follow_redirects=False,
            # Identify ourselves; never pose as a browser.
            headers={"User-Agent": settings.fetch_user_agent},
            limits=httpx.Limits(
                max_connections=max(1, settings.http_fetch_concurrency),
                keepalive_expiry=30.0,
            ),
        )
    return _fetch_client


# SEARCH_PROVIDERS is tried in order, skipping ones without a key. DuckDuckGo
# scrapes HTML, so it runs only when listed explicitly. If every provider
# fails, recent results for the query are served from cache, marked stale.

_CACHE: dict[str, tuple[float, str, list[dict]]] = {}
_CACHE_MAX = 500


def _key_for(name: str) -> str:
    """Per-provider key; SEARCH_API_KEY stands in for SEARCH_PROVIDER."""
    explicit = getattr(settings, f"{name}_api_key", "") or ""
    if explicit:
        return explicit
    return settings.search_api_key if name == settings.search_provider else ""


def search_chain() -> list[dict]:
    """Effective order with configuration status."""
    names = [
        n.strip().lower() for n in settings.search_providers.split(",") if n.strip()
    ]
    if not names:
        names = [settings.search_provider]
    out = []
    for name in dict.fromkeys(names):
        if name not in SEARCH_BACKENDS:
            continue
        keyless = name == "duckduckgo"
        out.append({"name": name, "configured": keyless or bool(_key_for(name))})
    return out


async def _tavily(query: str, max_results: int) -> list[dict]:
    async with _search_sem():
        resp = await search_client().post(
            "https://api.tavily.com/search",
            json={
                "api_key": _key_for("tavily"),
                "query": query,
                "max_results": max_results,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return [
        {"title": r["title"], "url": r["url"], "snippet": r.get("content", "")}
        for r in data.get("results", [])
    ]


async def _brave(query: str, max_results: int) -> list[dict]:
    async with _search_sem():
        resp = await search_client().get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": _key_for("brave"),
            },
            params={"q": query, "count": max_results},
        )
        resp.raise_for_status()
        data = resp.json()
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("description", ""),
        }
        for r in (data.get("web") or {}).get("results", [])
    ]


async def _duckduckgo(query: str, max_results: int) -> list[dict]:
    """Keyless HTML endpoint: lower quality and rate-limited."""
    from urllib.parse import parse_qs, urlparse

    from lxml import html as lxml_html

    async with _search_sem():
        resp = await search_client().post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": settings.fetch_user_agent},
        )
        resp.raise_for_status()
        body = resp.text
    tree = await asyncio.to_thread(lxml_html.fromstring, body)
    out = []

    def has_class(cls: str) -> str:
        return f"contains(concat(' ', normalize-space(@class), ' '), ' {cls} ')"

    for node in tree.xpath(f"//div[{has_class('result')}]")[: max_results * 2]:
        link = node.xpath(f".//a[{has_class('result__a')}]")
        if not link:
            continue
        href = link[0].get("href", "")
        # Result links are redirects (/l/?uddg=<target>); unwrap them.
        target = parse_qs(urlparse(href).query).get("uddg", [href])[0]
        if not target.startswith("http"):
            continue
        snippet = node.xpath(f".//*[{has_class('result__snippet')}]")
        out.append(
            {
                "title": link[0].text_content().strip(),
                "url": target,
                "snippet": snippet[0].text_content().strip() if snippet else "",
            }
        )
        if len(out) >= max_results:
            break
    return out


SEARCH_BACKENDS = {"tavily": _tavily, "brave": _brave, "duckduckgo": _duckduckgo}


def _cache_put(query: str, source: str, results: list[dict]) -> None:
    import time

    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[query.strip().lower()] = (time.monotonic(), source, results)


def _cache_get(query: str) -> tuple[str, list[dict]] | None:
    import time

    hit = _CACHE.get(query.strip().lower())
    if hit is None or time.monotonic() - hit[0] > settings.search_cache_seconds:
        return None
    return hit[1], hit[2]


class SearchUnavailable(RuntimeError):
    """Every provider failed and nothing recent is cached."""


def reusable_search(query: str) -> list[dict] | None:
    """Results of an identical query within SEARCH_REUSE_SECONDS, or None."""
    import time

    hit = _CACHE.get(query.strip().lower())
    if hit is None or time.monotonic() - hit[0] > settings.search_reuse_seconds:
        return None
    return [{**r, "source": f"cache:{hit[1]}"} for r in hit[2]]


def brief_results(results: list[dict]) -> list[dict]:
    """The first SEARCH_RESULTS_FOR_MODEL, snippets cut at a word boundary."""
    limit = max(1, settings.search_results_for_model)
    chars = max(40, settings.search_snippet_chars)
    out = []
    for r in results[:limit]:
        snippet = " ".join(str(r.get("snippet") or "").split())
        if len(snippet) > chars:
            snippet = snippet[:chars].rsplit(" ", 1)[0] + "…"
        out.append({**r, "snippet": snippet})
    return out


async def search_web(query: str, max_results: int = 8) -> list[dict]:
    reused = reusable_search(query)
    if reused is not None:
        return reused[:max_results]
    tried: list[str] = []
    for entry in search_chain():
        name = entry["name"]
        if not entry["configured"]:
            continue
        try:
            results = await SEARCH_BACKENDS[name](query, max_results)
        except Exception as exc:  # noqa: BLE001 - next provider in the chain
            tried.append(f"{name} ({type(exc).__name__})")
            continue
        if results:
            _cache_put(query, name, results)
            return [{**r, "source": name} for r in results]
        tried.append(f"{name} (no results)")
    cached = _cache_get(query)
    if cached is not None:
        source, results = cached
        return [{**r, "source": f"cache:{source}", "stale": True} for r in results]
    if not tried:
        raise SearchUnavailable(
            "No search provider is configured. Set SEARCH_PROVIDERS / provider keys, "
            "or work from URLs you already know with fetch_page."
        )
    raise SearchUnavailable(
        "Web search is unavailable right now (tried: " + ", ".join(tried) + "). "
        "Work from URLs you already have with fetch_page, or report what's missing."
    )


async def fetch_page(url: str, max_chars: int = 6000, offset: int = 0) -> str:
    """Cleaned page text; unfetchable pages return a guidance string, never raise.
    Long text ends with a note giving the `offset` to read on from (served from cache)."""
    offset = max(int(offset or 0), 0)
    cached = _page_cache_get(url)
    if cached is not None:
        return _window(cached, offset, max_chars)
    full, unavailable = await _fetch_text(url)
    if unavailable is not None:
        return unavailable
    _page_cache_put(url, full)
    return _window(full, offset, max_chars)


def _window(text: str, offset: int, max_chars: int) -> str:
    chunk = text[offset : offset + max_chars]
    rest = len(text) - (offset + max_chars)
    if rest > 0:
        chunk += (
            f"\n[... {rest} more characters. Call fetch_page with the same url and "
            f"offset={offset + max_chars} to read on.]"
        )
    return chunk


async def _fetch_text(url: str) -> tuple[str, str | None]:
    """(text with any archive note, None), or ("", guidance) when unreadable."""
    html = await _get_page_text(url)
    note = ""
    if html.startswith(_BLOCKED_PREFIX):
        return "", html
    if html.startswith("[Could not fetch ") and "archive" in _fetch_chain():
        # University pages change slowly, so a recent archive copy beats none.
        archived = await _get_page_text(f"https://web.archive.org/web/2/{url}")
        if not archived.startswith("[Could not fetch "):
            html = archived
            note = "[Live page unavailable; this is the Internet Archive's latest copy and may be out of date.]\n\n"
    if html.startswith("[Could not fetch "):
        return "", html

    # CPU-bound parsing of megabyte pages would freeze the event loop.
    text = await asyncio.to_thread(_extract, html, url)
    return note + text, None


_PAGES: TTLCache[str] = TTLCache(256, lambda: settings.fetch_cache_seconds)


def _page_cache_get(url: str) -> str | None:
    return _PAGES.get(url)


def _page_cache_put(url: str, text: str) -> None:
    _PAGES.put(url, text)


def _fetch_chain() -> list[str]:
    return [n.strip().lower() for n in settings.fetch_fallbacks.split(",") if n.strip()]


def _extract(html: str, base_url: str = "") -> str:
    text = trafilatura.extract(html, include_links=True) or ""
    people = _people_links_missing(html, text, base_url)
    if len(people) >= _MIN_MISSING_PEOPLE:
        # trafilatura drops names that are profile links on directory cards.
        text = (
            "People linked on this page (names the page text below leaves out):\n"
            + "\n".join(people)
            + "\n\n"
            + text
        )
    from api.prospects import profile_ids

    profile_ids.remember(html, base_url)
    images = _page_images(html, base_url)
    if images:
        # trafilatura drops images; listed first so later windows don't hide them.
        text = "Images on this page (exact URLs):\n" + "\n".join(images) + "\n\n" + text
    return text


#: Images listed per page; portraits past this are still remembered.
_MAX_IMAGES_LISTED = 8
#: Smaller than this (by width/height attributes) is an icon, not a picture.
_MIN_IMAGE_SIDE = 48
_LOGO_HINT = re.compile(r"logo|crest|emblem|seal", re.IGNORECASE)
_SKIP_IMAGE = re.compile(
    r"spacer|pixel|blank|sprite|icon|arrow|loading|placeholder|banner-ad|"
    r"facebook|twitter|linkedin|instagram|youtube|tiktok|weibo|wechat",
    re.IGNORECASE,
)
_PORTRAIT_WORDS = re.compile(
    r"^(photo|picture|image|portrait|headshot)\s+of\s+|"
    r"[\s,-]+(photo|picture|image|portrait|headshot)$",
    re.IGNORECASE,
)
_SECOND_LEVEL = {"ac", "edu", "co", "org", "gov", "net", "or", "go", "ne", "re"}

# "<site>|<name>" -> portrait URL, so a later save gets the photo without fetching.
_PORTRAITS: TTLCache[str] = TTLCache(5000, lambda: 86400.0)


def _site(host: str) -> str:
    """Registrable part: two labels, three under "ac.jp"-style second-level domains."""
    labels = host.lower().split(":")[0].removeprefix("www.").split(".")
    take = 3 if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in _SECOND_LEVEL else 2
    return ".".join(labels[-take:])


def _portrait_key(host: str, name: str) -> str:
    from api.core.textnorm import normalize_text

    return f"{_site(host)}|{normalize_text(name)}"


def portrait_for(name: str, page_urls: list[str | None]) -> str | None:
    from urllib.parse import urlparse

    clean = _person_name(name) or name
    for url in page_urls:
        host = urlparse(url).netloc if url else ""
        if host:
            hit = _PORTRAITS.get(_portrait_key(host, clean))
            if hit:
                return hit
    return None


def _page_images(html: str, base_url: str) -> list[str]:
    """Social image, logos, then pictures with alt text; pictures whose alt
    text is a person's name are remembered as their portrait."""
    from urllib.parse import urljoin, urlparse

    from lxml import html as lxml_html

    try:
        doc = lxml_html.fromstring(html)
    except (ValueError, TypeError, lxml_html.etree.ParserError):
        return []
    host = urlparse(base_url).netloc if base_url else ""

    def absolute(src: str | None) -> str | None:
        src = (src or "").strip()
        if not src or src.startswith("data:"):
            return None
        url = urljoin(base_url, src) if base_url else src
        return url if url.lower().startswith(("https://", "http://")) else None

    seen: set[str] = set()
    out: list[str] = []

    def add(url: str | None, label: str = "", alt: str = "") -> None:
        if url is None or url in seen or len(out) >= _MAX_IMAGES_LISTED:
            return
        seen.add(url)
        out.append(f"- {label}{url}" + (f' (alt "{alt}")' if alt else ""))

    for meta in doc.iter("meta"):
        if (meta.get("property") or meta.get("name") or "").lower() in ("og:image", "twitter:image"):
            add(absolute(meta.get("content")), "page image: ")
            break
    for img in doc.iter("img"):
        srcset = (img.get("srcset") or "").strip().split(" ")[0]
        url = absolute(img.get("src") or img.get("data-src") or srcset)
        if url is None:
            continue
        alt = " ".join((img.get("alt") or "").split())[:80]
        hints = " ".join((url, alt, img.get("class") or "", img.get("id") or ""))
        if _LOGO_HINT.search(hints):
            add(url, "logo: ", alt)
            continue
        if _SKIP_IMAGE.search(hints) or _tiny(img):
            continue
        name = _person_name(_PORTRAIT_WORDS.sub("", alt)) if alt else None
        if name and host:
            _PORTRAITS.put(_portrait_key(host, name), url)
        add(url, "", alt)
    return out


def _tiny(img) -> bool:
    for side in ("width", "height"):
        value = (img.get(side) or "").strip().removesuffix("px")
        if value.isdigit() and int(value) < _MIN_IMAGE_SIDE:
            return True
    return False


#: At least this many person-like links missing from the extracted text
#: before they are listed (a directory, not a homepage naming coauthors).
_MIN_MISSING_PEOPLE = 3
_MAX_PEOPLE_LISTED = 300
_HONORIFIC = re.compile(r"^(prof(essor)?|dr|mr|mrs|ms|mx)\.?\s+", re.IGNORECASE)
_DEGREE_SUFFIX = re.compile(r",?\s+(ph\.?\s?d|m\.?d|m\.?sc|dphil)\.?$", re.IGNORECASE)
_NAME_PARTICLES = {
    "van", "von", "de", "der", "den", "da", "di", "del", "della", "du", "la",
    "le", "bin", "binti", "ibn", "al", "el", "dos", "das", "do", "y", "e",
}  # fmt: skip
_NOT_NAME_WORDS = {
    "home", "about", "news", "events", "contact", "people", "faculty", "staff",
    "research", "apply", "admissions", "login", "log", "search", "menu",
    "directory", "students", "student", "alumni", "more", "read", "view",
    "profile", "website", "email", "department", "school", "university",
    "college", "program", "programs", "programme", "programmes", "courses",
    "overview", "publications", "lab", "labs", "group", "groups", "centre",
    "center", "institute", "jobs", "careers", "giving", "donate", "library",
    "map", "privacy", "accessibility", "emeritus", "adjunct", "graduate",
    "undergraduate", "teaching", "seminars", "seminar", "next", "previous",
    "back", "top", "skip", "main", "content", "cookie", "cookies", "policy",
    "terms", "visit", "give", "calendar", "resources", "facilities", "office",
    "phd", "masters", "postdoc", "postdocs", "visiting", "affiliated",
}  # fmt: skip


def _person_name(label: str) -> str | None:
    """`label` as a person's name, or None when it doesn't look like one:
    2-5 words, at least two capitalised, no digits, no navigation words."""
    name = _DEGREE_SUFFIX.sub("", _HONORIFIC.sub("", label.strip(" ,;|"))).strip(" ,")
    words = name.split()
    if not 2 <= len(words) <= 5 or len(name) > 60:
        return None
    capitals = 0
    for word in words:
        bare = word.strip(".,()").lower()
        if bare in _NOT_NAME_WORDS or any(ch.isdigit() for ch in word):
            return None
        if bare in _NAME_PARTICLES:
            continue
        if not word[:1].isalpha() or not word[:1].isupper():
            return None
        capitals += 1
    return name if capitals >= 2 else None


def _people_links_missing(html: str, text: str, base_url: str) -> list[str]:
    """Person-like link texts on the page that the extracted text lacks,
    as "Name (link)" lines, same-site links only."""
    from urllib.parse import urljoin, urlparse

    from lxml import html as lxml_html

    try:
        doc = lxml_html.fromstring(html)
    except (ValueError, TypeError, lxml_html.etree.ParserError):
        return []
    host = urlparse(base_url).netloc if base_url else ""
    haystack = " ".join(text.split()).lower()
    seen: set[str] = set()
    out: list[str] = []
    for anchor in doc.iter("a"):
        name = _person_name(" ".join(anchor.text_content().split()))
        if name is None or name.lower() in seen or name.lower() in haystack:
            continue
        href = (anchor.get("href") or "").strip()
        link = urljoin(base_url, href) if base_url and href else href
        parsed = urlparse(link)
        if host and parsed.netloc and parsed.netloc != host:
            continue
        seen.add(name.lower())
        out.append(
            f"- {name} ({parsed.path or link})" if host else f"- {name} ({link})"
        )
        if len(out) >= _MAX_PEOPLE_LISTED:
            break
    return out


_BLOCKED_PREFIX = "[Could not fetch: "


#: origin -> (expires at, parser or None)
_ROBOTS: dict[str, tuple[float, object]] = {}
_ROBOTS_TTL = 3600.0
# A 5xx robots.txt disallows (RFC 9309), but only briefly.
_ROBOTS_ERROR_TTL = 60.0
_ROBOTS_MAX = 1000


def _robots_agent() -> str:
    """Product token robots.txt rules are matched against."""
    return (settings.fetch_user_agent.split("/", 1)[0] or "GraduatorBot").strip()


async def _robots_allows(url: str) -> bool:
    """Cached per origin; a missing or unreadable robots.txt allows (RFC 9309 for 4xx)."""
    import time
    from urllib.robotparser import RobotFileParser

    if not settings.respect_robots_txt:
        return True
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL:
        return True
    origin = f"{parsed.scheme}://{parsed.netloc.decode()}"
    cached = _ROBOTS.get(origin)
    now = time.monotonic()
    if cached is None or now > cached[0]:
        parser: RobotFileParser | None = None
        ttl = _ROBOTS_TTL
        for attempt in range(2):
            try:
                resp, text = await egress.safe_get(
                    fetch_client(), f"{origin}/robots.txt", max_bytes=512_000
                )
            except (httpx.HTTPError, egress.EgressBlocked):
                parser = None
                break
            if resp.status_code >= 500 and attempt == 0:
                continue  # one retry: a single 5xx is usually transient
            if resp.status_code == 200:
                parser = RobotFileParser()
                parser.parse(text.splitlines())
            elif resp.status_code >= 500:
                parser = RobotFileParser()
                parser.disallow_all = True
                ttl = _ROBOTS_ERROR_TTL
            break
        if len(_ROBOTS) >= _ROBOTS_MAX:
            _ROBOTS.pop(next(iter(_ROBOTS)))
        _ROBOTS[origin] = (now + ttl, parser)
        cached = _ROBOTS[origin]
    parser = cached[1]
    return parser is None or bool(parser.can_fetch(_robots_agent(), url))  # type: ignore[attr-defined]


async def _get_page_text(url: str) -> str:
    """Raw HTML, or guidance text on failure so a blocked page never kills the task.
    Public addresses only (api/core/egress.py), body capped, robots.txt honoured."""
    try:
        async with _fetch_sem():
            if not await _robots_allows(url):
                return (
                    f"{_BLOCKED_PREFIX}the site's robots.txt asks automated agents "
                    "not to read this page. Use another source.]"
                )
            resp, text = await egress.safe_get(
                fetch_client(), url, max_bytes=settings.fetch_max_bytes
            )
            resp.raise_for_status()
            return text
    except egress.EgressBlocked:
        return (
            f"{_BLOCKED_PREFIX}that address is not allowed. Only public http(s) "
            "pages can be read. Try a different source.]"
        )
    except httpx.HTTPStatusError as exc:
        return (
            f"[Could not fetch {url}: HTTP {exc.response.status_code} - "
            "the site may be blocking automated requests. Try a different source.]"
        )
    except httpx.HTTPError as exc:
        return f"[Could not fetch {url}: {type(exc).__name__}. Try a different source.]"
