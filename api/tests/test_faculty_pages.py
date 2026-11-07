import asyncio

import httpx
import pytest

from api.prospects import web
from tests.test_compliance import _mock_fetch, _public_dns

FIRST = ["Ada", "Grace", "Alan", "Barbara", "Edsger", "Donald", "Frances", "John"]
LAST = [
    "Lovelace",
    "Hopper",
    "Turing",
    "Liskov",
    "Dijkstra",
    "Knuth",
    "Allen",
    "Backus",
]
NAMES = [f"{f} {last}" for f in FIRST for last in LAST][:60]


def _cards(linked: bool) -> str:
    cards = []
    for n, name in enumerate(NAMES):
        heading = f'<a href="/people/p{n}">{name}</a>' if linked else name
        cards.append(
            f'<div class="card"><h3>{heading}</h3><p>Professor of Computer Science</p>'
            f"<p>p{n}@uni.example</p></div>"
        )
    nav = '<nav><a href="/">Home</a><a href="/research">Research</a><a href="/apply">Apply Now</a></nav>'
    return f"<html><body>{nav}<main><h1>Our Faculty</h1>{''.join(cards)}</main></body></html>"


@pytest.fixture(autouse=True)
def _fresh_caches():
    web._PAGES.clear()
    web._ROBOTS.clear()
    yield
    web._PAGES.clear()
    web._ROBOTS.clear()


def test_linked_name_cards_keep_every_name():
    text = web._extract(_cards(linked=True), "https://uni.example/people")
    assert text.startswith("People linked on this page")
    assert all(name in text for name in NAMES)
    assert "- Ada Lovelace (/people/p0)" in text
    assert "Home" not in text.split("\n\n")[0] and "Apply Now" not in text


def test_plain_name_cards_get_no_extra_list():
    text = web._extract(_cards(linked=False), "https://uni.example/people")
    assert "People linked on this page" not in text
    assert "Ada Lovelace" in text


def test_a_homepage_naming_a_coauthor_is_left_alone():
    html = (
        "<html><body><article><h1>Prof. Ada Lovelace</h1><p>I study analytical "
        'engines with <a href="/people/babbage">Charles Babbage</a>.</p>'
        "</article></body></html>"
    )
    assert "People linked" not in web._extract(html, "https://uni.example/ada")


def test_person_name_heuristic():
    assert web._person_name("Prof. Jane van der Berg, PhD") == "Jane van der Berg"
    assert web._person_name("Dr. María José García") == "María José García"
    for label in ["Faculty Directory", "Apply Now", "Room 204", "jane smith", "Smith"]:
        assert web._person_name(label) is None, label


def test_long_pages_read_on_with_an_offset(monkeypatch):
    _public_dns(monkeypatch)
    seen = _mock_fetch(monkeypatch, lambda req: httpx.Response(200, text=_cards(True)))
    first = asyncio.run(web.fetch_page("https://uni.example/people", max_chars=500))
    assert "offset=500" in first and len(seen) == 1
    second = asyncio.run(
        web.fetch_page("https://uni.example/people", max_chars=500, offset=500)
    )
    assert len(seen) == 1  # served from the page just extracted
    assert second and second != first


@pytest.mark.robots
def test_a_robots_5xx_is_retried_and_only_briefly_cached(monkeypatch):
    _public_dns(monkeypatch)
    robots = {"n": 0, "codes": [503, 200]}

    def handler(req):
        if req.url.path == "/robots.txt":
            code = robots["codes"][min(robots["n"], len(robots["codes"]) - 1)]
            robots["n"] += 1
            return httpx.Response(code, text="User-agent: *\nAllow: /\n")
        return httpx.Response(200, text="<p>Faculty list</p>")

    _mock_fetch(monkeypatch, handler)
    assert "robots.txt" not in asyncio.run(web.fetch_page("https://uni.example/a"))
    assert robots["n"] == 2

    web._ROBOTS.clear()
    robots.update(n=0, codes=[503])
    assert "robots.txt" in asyncio.run(web.fetch_page("https://uni.example/b"))
    expires, _ = web._ROBOTS["https://uni.example"]
    import time

    assert expires - time.monotonic() <= web._ROBOTS_ERROR_TTL
