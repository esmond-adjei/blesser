import asyncio

import pytest
from fastapi.testclient import TestClient

from api.agent.tools import ToolContext, dispatch
from api.core.db import SessionLocal
from api.main import app
from api.prospects import web
from api.prospects.models import Professor, Program, RunSchool, School
from api.prospects.tools import image_url
from api.runs.models import Run
from tests.conftest import TEST_USER_ID
from tests.grounding_helpers import ground
from tests.test_budgets import _make_run, _professor_input

PAGE = """<html><head>
<meta property="og:image" content="/media/campus.jpg">
</head><body>
<header><img src="/static/uni-logo.svg" alt="Uni of Examples"></header>
<img src="/icons/search.png" width="16" height="16" alt="Search">
<img src="data:image/png;base64,AAAA" alt="Inline">
<img src="/social/facebook.png" alt="Facebook">
<main><h1>Our Faculty</h1>
<div class="card"><img src="/people/ada.jpg" alt="Photo of Ada Lovelace"><h3>Ada Lovelace</h3></div>
<div class="card"><img data-src="/people/grace.jpg" alt="Prof. Grace Hopper"><h3>Grace Hopper</h3></div>
<p>Professor of Computer Science, working on compilers and analytical engines.</p>
</main></body></html>"""


@pytest.fixture(autouse=True)
def _fresh_portraits():
    web._PORTRAITS.clear()
    yield
    web._PORTRAITS.clear()


def test_fetch_page_lists_useful_images_first():
    text = web._extract(PAGE, "https://cs.uni.ac.jp/people")
    head = text.split("\n\n")[0].splitlines()
    assert head[0] == "Images on this page (exact URLs):"
    assert head[1] == "- page image: https://cs.uni.ac.jp/media/campus.jpg"
    assert head[2] == '- logo: https://cs.uni.ac.jp/static/uni-logo.svg (alt "Uni of Examples")'
    assert '- https://cs.uni.ac.jp/people/ada.jpg (alt "Photo of Ada Lovelace")' in head
    assert '- https://cs.uni.ac.jp/people/grace.jpg (alt "Prof. Grace Hopper")' in head
    assert not any("search.png" in line or "facebook" in line or "data:" in line for line in head)


def test_pages_without_images_are_unchanged():
    text = web._extract("<html><body><p>Admissions open in March.</p></body></html>", "https://uni.example/")
    assert "Images on this page" not in text


def test_portraits_are_found_from_another_page_of_the_same_site():
    web._extract(PAGE, "https://cs.uni.ac.jp/people")
    assert web.portrait_for("Ada Lovelace", ["https://www.uni.ac.jp/"]) == "https://cs.uni.ac.jp/people/ada.jpg"
    assert web.portrait_for("Dr. Grace Hopper", [None, "https://cs.uni.ac.jp/x"]) == "https://cs.uni.ac.jp/people/grace.jpg"
    assert web.portrait_for("Ada Lovelace", ["https://www.other.ac.jp/"]) is None


@pytest.mark.parametrize(
    ("value", "kept"),
    [
        ("https://uni.example/a.jpg", "https://uni.example/a.jpg"),
        ("  http://uni.example/a.jpg ", "http://uni.example/a.jpg"),
        ("javascript:alert(1)", None),
        ("data:image/png;base64,AAAA", None),
        ("/relative/a.jpg", None),
        ("https://uni.example/" + "a" * 3000, None),
        (42, None),
    ],
)
def test_image_urls_are_plain_http_links(value, kept):
    assert image_url(value) == kept


def test_save_program_keeps_the_school_image():
    run_id = _make_run()

    async def saves():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            ctx = ToolContext(session=session, run=run)
            first = await dispatch(
                "save_program",
                {"school_name": "Uni A", "program_name": "PhD A", "school_image_url": "javascript:x"},
                ctx,
            )
            await dispatch(
                "save_program",
                {"school_name": "Uni A", "program_name": "PhD B", "school_image_url": "https://a.example/logo.png"},
                ctx,
            )
            await dispatch(
                "save_program",
                {"school_name": "Uni A", "program_name": "PhD C", "school_image_url": "https://a.example/other.png"},
                ctx,
            )
            return first["school_id"]

    school_id = asyncio.run(saves())
    body = TestClient(app).get(f"/api/schools/{school_id}").json()
    assert body["image_url"] == "https://a.example/logo.png"


def test_professor_gets_the_portrait_from_the_faculty_listing():
    run_id = _make_run()

    async def setup():
        async with SessionLocal() as session:
            school = School(
                user_id=TEST_USER_ID, run_links=[RunSchool(run_id=run_id)], name="Uni of Examples", website_url="https://www.uni.ac.jp/"
            )
            session.add(school)
            await session.flush()
            program = Program(
                user_id=TEST_USER_ID,
                school_id=school.id,
                name="PhD in CS",
                department_url="https://cs.uni.ac.jp/people",
            )
            session.add(program)
            await session.commit()
            return program.id

    program_id = asyncio.run(setup())
    # The supervisor read the listing; the worker saving Ada never did.
    web._extract(PAGE, "https://cs.uni.ac.jp/people")

    async def save():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            program = await session.get(Program, program_id)
            ctx = ToolContext(session=session, run=run, program=program)
            payload = _professor_input(3)
            payload["name"] = "Ada Lovelace"
            result = await dispatch("save_professor_record", ground(ctx, payload), ctx)
            stored = await session.get(Professor, result["professor_id"])
            return stored.photo_url

    assert asyncio.run(save()) == "https://cs.uni.ac.jp/people/ada.jpg"
