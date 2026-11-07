import asyncio
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader

from api.applications.models import Application
from api.candidates.models import CandidateScore
from api.core.db import SessionLocal
from api.exports import pdf
from api.exports import service as export_service
from api.main import app
from api.outreach.models import EmailDraft
from api.prospects.models import Paper, Professor, Program, RunSchool, School
from api.runs.models import Run
from tests.conftest import TEST_USER_ID

# The real fetcher, before the autouse stub below replaces it.
REAL_FETCH_PHOTO = export_service.fetch_photo


def _seed(name: str, score: float, *, user_id: str = TEST_USER_ID, with_extras: bool = True) -> str:
    async def go():
        async with SessionLocal() as session:
            run = Run(
                user_id=user_id,
                region="Japan",
                field="computer vision",
                degree_level="phd",
                interest_statement="relighting",
                status="running",
            )
            session.add(run)
            await session.flush()
            school = School(user_id=user_id, run_links=[RunSchool(run_id=run.id)], name="Chubu University")
            session.add(school)
            await session.flush()
            program = Program(user_id=user_id, school_id=school.id, name="PhD in Computer Science")
            session.add(program)
            await session.flush()
            prof = Professor(
                user_id=user_id,
                program_id=program.id,
                name=name,
                email="prof@chubu.example",
                lab_name="Vision Lab",
                bio="Works on inverse rendering and relighting.",
                bio_source="faculty",
                photo_url="https://photos.example/p.jpg",
                socials=[{"label": "Scholar", "url": "https://scholar.example/p"}],
            )
            session.add(prof)
            await session.flush()
            session.add(
                Paper(
                    user_id=user_id,
                    professor_id=prof.id,
                    title="Neural relighting of reconstructed indoor scenes",
                    abstract="We relight radiance fields.",
                    year=2024,
                    url="https://papers.example/1",
                )
            )
            cand = CandidateScore(
                user_id=user_id,
                run_id=run.id,
                professor_id=prof.id,
                similarity_score=score,
                rationale="Strong fit: **Neural relighting** matches the interest.",
                status="drafted",
            )
            session.add(cand)
            await session.flush()
            if with_extras:
                session.add(
                    EmailDraft(
                        user_id=user_id,
                        candidate_id=cand.id,
                        subject="Prospective PhD student: scene relighting",
                        body="Dear Professor,\n\nI read your paper.\n\nBest,\nKwame",
                    )
                )
                session.add(
                    Application(
                        user_id=user_id,
                        school="Chubu University",
                        program="PhD in CS",
                        deadline="2026-12-01",
                        requirements=[{"label": "Statement of purpose", "done": True}],
                        professors=[{"name": name, "candidate_id": cand.id}],
                    )
                )
            await session.commit()
            return cand.id

    return asyncio.run(go())


@pytest.fixture(autouse=True)
def _no_photo_fetch(monkeypatch):
    async def none(url):
        return None

    monkeypatch.setattr(export_service, "fetch_photo", none)


def _text(body: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(body)).pages)


def test_one_candidate_exports_their_dossier():
    cid = _seed("Ada Lovelace", 0.82)
    resp = TestClient(app).post("/api/candidates/export.pdf", json={"candidate_ids": [cid]})
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert 'filename="graduator-ada-lovelace.pdf"' in resp.headers["content-disposition"]
    assert resp.content.startswith(b"%PDF")
    text = _text(resp.content)
    for expected in (
        "Ada Lovelace",
        "Chubu University",
        "82%",
        "STRONG MATCH",
        "WHY THIS MATCH",
        "Neural relighting",
        "CITED PAPERS",
        "OUTREACH EMAIL",
        "Prospective PhD student: scene relighting",
        "APPLICATION",
        "2026-12-01",
        "Statement of purpose",
        "Works on inverse rendering",
    ):
        assert expected in text, expected
    assert "Contents" not in text  # one candidate: no cover or contents


def test_several_candidates_share_one_document_strongest_first():
    weak = _seed("Grace Hopper", 0.41, with_extras=False)
    strong = _seed("Alan Turing", 0.9, with_extras=False)
    resp = TestClient(app).post("/api/candidates/export.pdf", json={"candidate_ids": [weak, strong]})
    assert resp.status_code == 200, resp.text
    assert "graduator-dossier-" in resp.headers["content-disposition"]
    reader = PdfReader(io.BytesIO(resp.content))
    contents = reader.pages[1].extract_text()
    assert "Contents" in contents
    assert contents.index("Alan Turing") < contents.index("Grace Hopper")
    assert [o.title for o in reader.outline] == ["Alan Turing", "Grace Hopper"]
    assert f"of {len(reader.pages)}" in reader.pages[-1].extract_text()


def test_only_your_own_candidates():
    other = "someone-else-0000"

    async def make_other_user():
        from api.auth.models import User

        async with SessionLocal() as session:
            if await session.get(User, other) is None:
                session.add(User(id=other, email="else@example.com", password_hash="!"))
                await session.commit()

    asyncio.run(make_other_user())
    theirs = _seed("Hidden Person", 0.7, user_id=other, with_extras=False)
    client = TestClient(app)
    assert client.post("/api/candidates/export.pdf", json={"candidate_ids": [theirs]}).status_code == 404
    assert client.post("/api/candidates/export.pdf", json={"candidate_ids": []}).status_code == 422


def test_text_in_other_scripts_gets_a_font_that_has_it():
    markup = pdf.rich("山田 太郎 and Ада")
    assert '<font name="STSong-Light">山田</font>' in markup
    assert " and " in markup
    assert "HeiseiKakuGo-W5" in pdf.rich("やまだ 太郎")
    assert pdf.rich("Smith – “Notes”…") == "Smith – “Notes”…"
    body = pdf.build_pdf(
        [pdf.Dossier(id="x", name="山田 太郎", school="東京大学", program="情報", status="scored", score=0.5)],
        title="山田 太郎",
        subtitle="東京大学",
        prepared="Prepared for you",
    )
    assert body.startswith(b"%PDF")


def test_markdown_from_agents_becomes_formatted_text():
    styles = pdf._styles()
    flows = pdf.markdown_paragraphs(
        "Strong **fit**, see [lab](https://lab.example).\n\n- one\n- two",
        styles["body"],
        styles["bullet"],
    )
    assert len(flows) == 3
    assert "<b>fit</b>" in flows[0].text and 'href="https://lab.example"' in flows[0].text


@pytest.mark.parametrize("url", [None, "", "ftp://x.example/a.jpg", "http://127.0.0.1/p.jpg", "http://10.0.0.5/p.jpg"])
def test_photos_come_only_from_public_web_addresses(url):
    assert asyncio.run(REAL_FETCH_PHOTO(url)) is None


def test_photos_are_cropped_to_a_small_square():
    im = Image.new("RGB", (600, 900), (200, 100, 50))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    out = export_service._square_jpeg(buf.getvalue())
    with Image.open(io.BytesIO(out)) as small:
        assert small.size == (export_service.PHOTO_SIDE, export_service.PHOTO_SIDE)
        assert small.format == "JPEG"
    assert export_service._square_jpeg(b"not an image") is None


def test_only_web_and_mail_links_become_clickable():
    assert pdf._href("https://uni.example/a") == "https://uni.example/a"
    assert pdf._href("mailto:a@uni.example") == "mailto:a@uni.example"
    assert pdf._href("javascript:alert(1)") is None
    assert pdf._href("file:///etc/passwd") is None
    assert "<link" not in pdf._link("Profile", "javascript:alert(1)")


def test_a_non_latin_name_in_the_page_band_and_odd_years_render():
    body = pdf.build_pdf(
        [
            pdf.Dossier(
                id="x",
                name="Иван Петров",
                school="Skoltech",
                program="PhD",
                status="scored",
                score=0.5,
                papers=[{"title": "A <b> paper", "year": "<2024>", "url": "javascript:x"}],
            )
        ],
        title="Иван Петров",
        subtitle="Skoltech",
        prepared="Prepared for Иван",
    )
    assert body.startswith(b"%PDF")
    assert "<2024>" in _text(body)


def test_a_non_latin_name_in_the_page_band_gets_a_font_that_has_it():
    # The band must draw a CJK name through rich(), or it comes out as boxes.
    buf = io.BytesIO()
    c = pdf.pdf_canvas.Canvas(buf, pagesize=pdf.A4)
    pdf._draw_band(c, "山田 太郎")
    c.showPage()
    c.save()
    assert b"STSong-Light" in buf.getvalue()


def test_images_that_decode_too_large_are_skipped(monkeypatch):
    monkeypatch.setattr(export_service, "PHOTO_MAX_PIXELS", 1000)
    im = Image.new("RGB", (100, 100))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    assert export_service._square_jpeg(buf.getvalue()) is None
