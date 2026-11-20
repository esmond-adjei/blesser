"""PDF calls: safe fetching, sandboxed text extraction, triage and seeded sources."""

import asyncio
import io
import uuid
from types import SimpleNamespace

import httpx
import pytest
from pypdf import PdfWriter
from pypdf.annotations import Link
from pypdf.generic import DictionaryObject, NameObject, StreamObject
from sqlalchemy import select

from api import web
from api.core import egress
from api.core.config import settings
from api.core.db import SessionLocal
from api.opportunities import crawl_http, page_cache, pdf_text
from api.opportunities.crawl_models import Source
from api.opportunities.crawler import parse_items
from api.opportunities.page_content import Page, deadline_dates
from api.opportunities.pdf_text import PdfBody, read_pdf
from api.opportunities.triage import triage_page

PUBLIC = "93.184.216.34"
CALL = [
    "Ghana Research Grant 2027",
    "The Accra Research Council invites applications from researchers in Ghana.",
    "Eligibility: early career researchers at Ghanaian universities.",
    "Application deadline: 30 April 2027",
]


def run(coro):
    return asyncio.run(coro)


def make_pdf(lines=CALL, *, title="", link=None, password=None, owner_only=False):
    writer = PdfWriter()
    page = writer.add_blank_page(612, 792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    if lines:
        ops = "BT /F1 11 Tf 50 750 Td 14 TL "
        ops += " ".join(f"({line}) '" for line in lines) + " ET"
        stream = StreamObject()
        stream.set_data(ops.encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    if title:
        writer.add_metadata({"/Title": title})
    if link:
        writer.add_annotation(0, Link(rect=(50, 50, 200, 70), url=link))
    if password or owner_only:
        writer.encrypt(user_password=password or "", owner_password="owner")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def url(path=""):
    return f"https://example.org/{uuid.uuid4().hex}{path}"


def test_pdf_text_title_links_and_deadline_are_read():
    source = url(".pdf")
    page = run(
        read_pdf(
            PdfBody(make_pdf(title="Ghana Research Grant", link="https://x.org/apply")),
            source,
        )
    )
    assert not page.error
    assert page.title == "Ghana Research Grant"
    assert "invites applications from researchers in Ghana" in page.text
    assert "https://x.org/apply" in page.text
    assert page.metadata["format"] == "pdf" and page.metadata["pdf_pages"] == 1
    # PDFs never expand into more candidates.
    assert page.metadata["links"] == []
    assert [d.isoformat() for d in deadline_dates(page.text)] == ["2027-04-30"]
    assert len(page.content_hash) == 64


def test_pdf_title_falls_back_to_first_line():
    page = run(read_pdf(PdfBody(make_pdf()), url(".pdf")))
    assert page.title == "Ghana Research Grant 2027"


@pytest.mark.parametrize(
    ("body", "error"),
    [
        (PdfBody(make_pdf(), truncated=True), "pdf_too_large"),
        (PdfBody(make_pdf(password="secret")), "pdf_encrypted"),
        (PdfBody(b"%PDF-1.7\n" + b"\x00garbage" * 200), "pdf_unreadable"),
        (PdfBody(b"<html>not a pdf</html>"), "pdf_unreadable"),
        (PdfBody(make_pdf(lines=[])), "pdf_no_text"),
        (PdfBody(make_pdf(lines=["Scan"])), "pdf_no_text"),
    ],
)
def test_unusable_pdfs_become_stable_error_codes(body, error):
    assert run(read_pdf(body, url(".pdf"))).error == error


def test_owner_locked_pdf_with_empty_user_password_is_read():
    page = run(read_pdf(PdfBody(make_pdf(owner_only=True)), url(".pdf")))
    assert not page.error and "Ghana Research Grant" in page.text


def test_oversized_body_is_refused_before_parsing(monkeypatch):
    monkeypatch.setattr(settings, "pdf_max_bytes", 100)

    async def never(*args, **kwargs):
        raise AssertionError("an oversized PDF must not reach the parser")

    monkeypatch.setattr(pdf_text, "run_child", never)
    assert run(read_pdf(PdfBody(make_pdf()), url(".pdf"))).error == "pdf_too_large"


def test_slow_parser_is_killed(monkeypatch):
    monkeypatch.setattr(settings, "pdf_timeout_seconds", 0.001)
    assert run(read_pdf(PdfBody(make_pdf()), url(".pdf"))).error == "pdf_timeout"


def test_parser_runs_under_a_memory_limit(monkeypatch):
    pytest.importorskip("resource")
    # Far too little memory to load the parser: the child must fail closed.
    monkeypatch.setattr(settings, "pdf_memory_mb", 8)
    error = run(read_pdf(PdfBody(make_pdf()), url(".pdf"))).error
    assert error in {"pdf_too_large", "pdf_unreadable"}


def _serve(monkeypatch, handler):
    async def resolve(host, port):
        return [PUBLIC]

    async def reserve(*args):
        return None

    seen = []

    def record(request):
        seen.append(str(request.url))
        return handler(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(record))
    monkeypatch.setattr(egress, "_resolve", resolve)
    monkeypatch.setattr(crawl_http, "reserve_host", reserve)
    monkeypatch.setattr(web, "fetch_client", lambda: client)
    return seen


def _pdf_response(data, **headers):
    return lambda request: httpx.Response(200, headers=headers, content=data)


@pytest.mark.parametrize(
    ("path", "headers"),
    [
        ("/call", {"content-type": "application/pdf"}),
        ("/call.pdf", {"content-type": "application/octet-stream"}),
        ("/download?id=4", {}),
    ],
)
def test_get_document_returns_pdf_bytes(monkeypatch, path, headers):
    data = make_pdf()
    _serve(monkeypatch, _pdf_response(data, **headers))
    _, body = run(crawl_http.get_document(url(path), interval=0, allow_pdf=True))
    assert isinstance(body, PdfBody)
    assert body.data == data and not body.truncated


def test_get_document_keeps_html_and_feeds_as_text(monkeypatch):
    html = "<html><main>Accra Innovation Award</main></html>"
    _serve(monkeypatch, _pdf_response(html.encode(), **{"content-type": "text/html"}))
    _, body = run(crawl_http.get_document(url(), interval=0, allow_pdf=True))
    assert body == html
    # Source crawls never ask for PDFs and keep the text-only behaviour.
    _serve(
        monkeypatch, _pdf_response(make_pdf(), **{"content-type": "application/pdf"})
    )
    _, body = run(crawl_http.get_document(url(".pdf"), interval=0))
    assert isinstance(body, str)


def test_get_document_flags_pdfs_over_the_cap(monkeypatch):
    monkeypatch.setattr(settings, "pdf_max_bytes", 1000)
    data = make_pdf() + b"%" * 5000
    _serve(monkeypatch, _pdf_response(data, **{"content-type": "application/pdf"}))
    _, body = run(crawl_http.get_document(url(".pdf"), interval=0, allow_pdf=True))
    assert isinstance(body, PdfBody) and body.truncated
    assert len(body.data) <= 1000


def test_declared_oversize_pdf_is_not_downloaded(monkeypatch):
    monkeypatch.setattr(settings, "pdf_max_bytes", 1000)
    sent = []

    async def stream():
        for _ in range(50):
            sent.append(1)
            yield b"%PDF-1.7" + b"0" * 1000

    _serve(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            headers={"content-type": "application/pdf", "content-length": "50400"},
            content=stream(),
        ),
    )
    _, body = run(crawl_http.get_document(url(".pdf"), interval=0, allow_pdf=True))
    assert isinstance(body, PdfBody) and body.truncated
    assert len(sent) == 1


def test_page_cache_stores_pdf_text(monkeypatch):
    source = url(".pdf")
    calls = []

    async def fetch(target, **kwargs):
        calls.append(kwargs)
        return httpx.Response(200, request=httpx.Request("GET", target)), PdfBody(
            make_pdf()
        )

    monkeypatch.setattr(page_cache, "get_document", fetch)

    async def check():
        first = await page_cache.get_page(source)
        again = await page_cache.get_page(source)
        assert not first.error and "Ghana Research Grant" in first.text
        assert again.cached and again.text == first.text
        assert again.metadata["format"] == "pdf"
        assert len(calls) == 1 and calls[0]["allow_pdf"] is True

    run(check())


def test_unusable_pdf_is_rejected_not_retried():
    candidate = SimpleNamespace(id="c", url=url(".pdf"))

    async def check():
        for code in ("pdf_encrypted", "pdf_too_large", "pdf_no_text"):
            page = Page(url=candidate.url, error=code)
            assert await triage_page(None, candidate, page, None) == code
        page = Page(url=candidate.url, error="ConnectError")
        assert await triage_page(None, candidate, page, None) == (
            "fetch_failed:ConnectError"
        )

    run(check())


def test_listings_and_feeds_keep_pdf_calls():
    page = """<html><body><main>
      <a href="/files/call-for-proposals-2027.pdf">Download</a>
      <a href="/files/scholarship-notice.PDF">Scholarship notice (PDF)</a>
      <a href="/files/logo.png">Grant logo</a>
      <a href="/about">About us</a>
    </main></body></html>"""
    items, _ = parse_items(page, "https://uni.example/announcements", "listing", 10)
    assert [item["url"] for item in items] == [
        "https://uni.example/files/call-for-proposals-2027.pdf",
        "https://uni.example/files/scholarship-notice.PDF",
    ]
    feed = (
        "<rss><channel><item><title>Grant call</title>"
        "<link>https://uni.example/call.pdf</link></item></channel></rss>"
    )
    items, _ = parse_items(feed, "https://uni.example/feed", "rss", 10)
    assert [item["url"] for item in items] == ["https://uni.example/call.pdf"]


def test_ghana_sources_are_seeded():
    async def check():
        async with SessionLocal() as session:
            rows = {
                row.id: row
                for row in (
                    await session.execute(
                        select(Source).where(Source.id.startswith("seed-"))
                    )
                ).scalars()
            }
        authority = rows["seed-ghana-scholarships-authority"]
        assert authority.url == "https://scholarships.gov.gh/opportunities"
        assert authority.enabled and not authority.proposed
        assert authority.category_hints == ["student"]
        for key in ("ug-research-calls", "knust-announcements", "aref-funding-calls"):
            assert rows["seed-" + key].enabled
        for key in ("gea-expressions-of-interest", "getfund-scholarships"):
            assert not rows["seed-" + key].enabled

    run(check())
