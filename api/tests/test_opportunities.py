"""Opportunity catalogue, the grounded save_opportunity tool, tracking, to-dos and calendars."""

import asyncio
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update

from api.agent.tools import ToolContext
from api.applications.models import Application
from api.core.config import settings
from api.core.db import SessionLocal
from api.main import app
from api.opportunities import scans
from api.opportunities import service as opp_service
from api.opportunities import tasks as opp_tasks
from api.opportunities import tools as opp_tools
from api.opportunities.models import Opportunity
from api.runs.models import ResearchTask, Run
from api.todos import ics
from api.todos.models import CalendarFeed, Todo
from tests.conftest import TEST_USER_EMAIL, TEST_USER_ID


def _wipe():
    async def go():
        async with SessionLocal() as session:
            await session.execute(delete(Todo))
            await session.execute(delete(CalendarFeed))
            await session.execute(delete(Application))
            await session.execute(delete(Opportunity))
            await session.commit()

    asyncio.run(go())


@pytest.fixture(autouse=True)
def _clean():
    _wipe()
    yield
    _wipe()


def _client():
    return TestClient(app)


def _future(days: int) -> date:
    return opp_service.today() + timedelta(days=days)


def _add(**fields) -> str:
    """Insert a catalogue row directly; returns its id."""

    async def go():
        async with SessionLocal() as session:
            title = fields.pop("title", "Seed Fund")
            org = fields.pop("organization", "Accra Ventures")
            row = Opportunity(
                title=title,
                organization=org,
                category=fields.pop("category", "startup"),
                kind=fields.pop("kind", "grant"),
                summary=fields.pop("summary", ""),
                eligibility="",
                benefits="",
                location=fields.pop("location", "Ghana"),
                countries=fields.pop("countries", []),
                requirements=fields.pop("requirements", []),
                tags=fields.pop("tags", []),
                deadline="",
                rolling=fields.pop("rolling", False),
                link="https://example.org/apply",
                source_url="https://example.org/apply",
                status=fields.pop("status", "published"),
                source="agent",
                dedupe_key=opp_service.dedupe_key(org, title),
                **fields,
            )
            session.add(row)
            await session.commit()
            return row.id

    return asyncio.run(go())


# --- iCalendar ---------------------------------------------------------------


def test_ics_escapes_and_folds():
    body = ics.render(
        [
            ics.Event(
                uid="x@blesser",
                day=date(2026, 12, 15),
                summary="Deadline: Grants; loans, and more",
                description="Line one\nLine two " + "é" * 80,
            )
        ],
        name="Test",
        now=opp_service.utcnow_naive(),
    )
    assert body.startswith("BEGIN:VCALENDAR\r\n")
    assert body.endswith("END:VCALENDAR\r\n")
    assert "DTSTART;VALUE=DATE:20261215" in body
    assert "DTEND;VALUE=DATE:20261216" in body
    assert "SUMMARY:Deadline: Grants\\; loans\\, and more" in body
    assert "Line one\\nLine two" in body
    for line in body.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75
    assert "TRIGGER:-P7D" in body and "TRIGGER:-P1D" in body


# --- grounding helpers -----------------------------------------------------------


def test_url_key_ignores_cosmetic_differences():
    assert opp_tools.url_key("http://www.Example.org/apply/#top") == opp_tools.url_key(
        "https://example.org/apply"
    )


def test_names_opportunity_and_deadline_on_page():
    page = "The Ghana Climate Innovation Challenge is open. Apply by 30 June 2027."
    assert opp_tools.names_opportunity(page, "Ghana Climate Innovation Challenge", "")
    assert not opp_tools.names_opportunity(page, "Mars Rover Prize", "NASA")
    assert opp_tools.deadline_on_page(page, date(2027, 6, 30))
    assert not opp_tools.deadline_on_page(page, date(2028, 6, 30))


# --- save_opportunity -----------------------------------------------------------


def _run_id() -> str:
    async def go():
        async with SessionLocal() as session:
            run = Run(
                user_id=TEST_USER_ID,
                region="Ghana",
                field="Opportunities: startup",
                degree_level="either",
                interest_statement="-",
                status="running",
            )
            session.add(run)
            await session.commit()
            return run.id

    return asyncio.run(go())


PAGE = (
    "Accra Ventures Seed Fund 2027. Equity-free grants of up to USD 20,000 for "
    "Ghanaian startups. Applications close 15 March 2027."
)


def _save(run_id, tool_input, pages=None):
    async def go():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            ctx = ToolContext(session=session, run=run)
            for url, text in (pages or {}).items():
                opp_tools.record_fetch(ctx, url, text)
            return await opp_tools.handle_save_opportunity(tool_input, ctx)

    return asyncio.run(go())


BASE = {
    "title": "Accra Ventures Seed Fund",
    "organization": "Accra Ventures",
    "category": "startup",
    "kind": "grant",
    "summary": "Equity-free grants for early-stage startups.",
    "source_url": "https://accraventures.example/seed",
}


def test_save_requires_a_fetched_page():
    result = _save(_run_id(), BASE)
    assert "fetch_page" in result["error"]


def test_save_refuses_page_that_does_not_name_it():
    result = _save(
        _run_id(),
        {**BASE, "title": "Lunar Mining Prize", "organization": "Moon Corp"},
        {BASE["source_url"]: PAGE},
    )
    assert "doesn't name" in result["error"]


def test_save_refuses_deadline_missing_from_page_and_past_deadlines():
    run_id = _run_id()
    pages = {BASE["source_url"]: PAGE}
    wrong = _save(run_id, {**BASE, "deadline": "2027-09-01"}, pages)
    assert "isn't on the fetched page" in wrong["error"]
    past_page = PAGE + " Previous round closed 10 January 2020."
    past = _save(run_id, {**BASE, "deadline": "2020-01-10"}, {BASE["source_url"]: past_page})
    assert "passed" in past["error"]


def test_save_creates_then_refreshes_without_duplicating():
    run_id = _run_id()
    pages = {"https://www.accraventures.example/seed/": PAGE}
    first = _save(run_id, {**BASE, "deadline": "2027-03-15"}, pages)
    assert first["created"] is True
    assert first["deadline_date"] == "2027-03-15"
    assert first["status"] == "published"
    second = _save(
        run_id,
        {
            **BASE,
            "organization": "ACCRA VENTURES",
            "eligibility": "Ghana-registered startups",
            "tags": ["fintech"],
        },
        pages,
    )
    assert second["created"] is False
    assert second["opportunity_id"] == first["opportunity_id"]
    assert "eligibility" in second["updated_fields"]
    assert "tags" in second["updated_fields"]

    async def count():
        async with SessionLocal() as session:
            return len((await session.execute(select(Opportunity))).scalars().all())

    assert asyncio.run(count()) == 1


def test_save_respects_task_budget(monkeypatch):
    monkeypatch.setattr(settings, "max_opportunities_per_task", 0)
    result = _save(_run_id(), BASE, {BASE["source_url"]: PAGE})
    assert "Budget reached" in result["error"]


# --- public catalogue --------------------------------------------------------------


def test_public_list_filters_and_hides_unpublished_and_closed():
    soon = _add(title="Soon Grant", deadline_date=_future(3))
    later = _add(title="Later Grant", deadline_date=_future(40))
    rolling = _add(title="Rolling Fellowship", category="research", kind="fellowship", rolling=True)
    _add(title="Closed Grant", deadline_date=_future(-2))
    _add(title="Pending Grant", status="pending")
    _add(title="Hidden Grant", status="hidden")
    client = _client()

    body = client.get("/api/opportunities").json()
    assert [i["id"] for i in body["items"]] == [soon, later, rolling]
    assert body["total"] == 3
    assert body["items"][0]["days_left"] == 3 and body["items"][0]["is_open"]

    research = client.get("/api/opportunities", params={"category": "research"}).json()
    assert [i["id"] for i in research["items"]] == [rolling]
    closing = client.get("/api/opportunities", params={"closing_within": 7}).json()
    assert [i["id"] for i in closing["items"]] == [soon]
    with_closed = client.get("/api/opportunities", params={"include_closed": True}).json()
    assert with_closed["total"] == 4
    search = client.get("/api/opportunities", params={"q": "fellowship"}).json()
    assert [i["id"] for i in search["items"]] == [rolling]

    facets = client.get("/api/opportunities/facets").json()
    assert facets["total"] == 3
    assert {f["key"]: f["count"] for f in facets["categories"]} == {"startup": 2, "research": 1}
    assert facets["closing_soon"] == 1


def test_unpublished_opportunity_is_not_found():
    pending = _add(title="Pending Grant", status="pending")
    assert _client().get(f"/api/opportunities/{pending}").status_code == 404


def test_opportunity_ics_download():
    opp = _add(title="Soon Grant", deadline_date=date(2027, 3, 15))
    resp = _client().get(f"/api/opportunities/{opp}/calendar.ics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/calendar")
    assert "DTSTART;VALUE=DATE:20270315" in resp.text
    assert "SUMMARY:Deadline: Soon Grant (Accra Ventures)" in resp.text


def test_submission_waits_for_review_and_moderation_is_ops_only():
    client = _client()
    resp = client.post(
        "/api/opportunities",
        json={
            "title": "Community Hackathon",
            "organization": "Kumasi Hub",
            "category": "student",
            "kind": "competition",
            "link": "https://kumasihub.example/hack",
            "deadline": "2027-05-01",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["deadline_date"] == "2027-05-01"
    assert client.get("/api/opportunities").json()["total"] == 0
    denied = client.patch(f"/api/opportunities/{body['id']}/status", json={"status": "published"})
    assert denied.status_code == 403


def _set_verified(value):
    async def go():
        from api.auth.models import User

        async with SessionLocal() as session:
            user = await session.get(User, TEST_USER_ID)
            before = user.email_verified_at
            user.email_verified_at = value
            await session.commit()
            return before

    return asyncio.run(go())


def test_ops_admin_can_publish(monkeypatch):
    before = _set_verified(opp_service.utcnow_naive())
    try:
        monkeypatch.setattr(settings, "ops_admin_emails", TEST_USER_EMAIL)
        pending = _add(title="Pending Grant", status="pending")
        client = _client()
        assert [o["id"] for o in client.get("/api/opportunities/pending").json()] == [pending]
        resp = client.patch(f"/api/opportunities/{pending}/status", json={"status": "published"})
        assert resp.status_code == 200
        assert client.get("/api/opportunities").json()["total"] == 1
    finally:
        _set_verified(before)


# --- tracking --------------------------------------------------------------------


def test_track_copies_into_applications_once():
    opp = _add(
        title="Soon Grant",
        deadline_date=_future(10),
        requirements=["Pitch deck", "Financials"],
        summary="Money for founders.",
    )
    client = _client()
    first = client.post(f"/api/opportunities/{opp}/track")
    assert first.status_code == 200, first.text
    tracked = first.json()
    assert tracked["opportunity_id"] == opp
    assert tracked["school"] == "Accra Ventures"
    assert tracked["program"] == "Soon Grant"
    assert tracked["degree_type"] == "Grant"
    assert [r["label"] for r in tracked["requirements"]] == ["Pitch deck", "Financials"]
    assert tracked["deadline_date"] == _future(10).isoformat()
    again = client.post(f"/api/opportunities/{opp}/track").json()
    assert again["id"] == tracked["id"]
    assert client.get("/api/opportunities/tracked").json() == {opp: tracked["id"]}


# --- to-dos and the calendar feed -------------------------------------------------


def test_todo_crud_and_links():
    opp = _add(title="Soon Grant")
    client = _client()
    created = client.post(
        "/api/todos",
        json={"title": "Draft pitch deck", "due_date": "2027-01-10", "opportunity_id": opp},
    )
    assert created.status_code == 200, created.text
    todo = created.json()
    assert todo["opportunity_title"] == "Soon Grant"
    assert todo["priority"] == "normal" and todo["done"] is False

    bad = client.post("/api/todos", json={"title": "x", "application_id": "nope"})
    assert bad.status_code == 400

    done = client.patch(f"/api/todos/{todo['id']}", json={"done": True}).json()
    assert done["done"] is True and done["done_at"] is not None
    assert client.get("/api/todos").json() == []
    assert [t["id"] for t in client.get("/api/todos", params={"status": "done"}).json()] == [
        todo["id"]
    ]
    reopened = client.patch(f"/api/todos/{todo['id']}", json={"done": False}).json()
    assert reopened["done_at"] is None
    assert client.delete(f"/api/todos/{todo['id']}").status_code == 200
    assert client.get("/api/todos", params={"status": "all"}).json() == []


def test_calendar_feed_lists_deadlines_and_todos_and_rotates():
    client = _client()
    opp = _add(title="Soon Grant", deadline_date=_future(5))
    client.post(f"/api/opportunities/{opp}/track")
    client.post("/api/todos", json={"title": "Ask for references", "due_date": _future(2).isoformat()})
    client.post("/api/todos", json={"title": "Someday"})

    feed = client.get("/api/calendar/feed").json()
    assert feed["webcal_url"].startswith("webcal://")
    assert client.get("/api/calendar/feed").json()["url"] == feed["url"]
    path = "/api/calendar/feed/" + feed["url"].rsplit("/", 1)[1]
    body = client.get(path)
    assert body.status_code == 200
    assert "SUMMARY:Deadline: Accra Ventures\\, Soon Grant" in body.text
    assert "SUMMARY:To-do: Ask for references" in body.text
    assert "Someday" not in body.text

    rotated = client.post("/api/calendar/feed/rotate").json()
    assert rotated["url"] != feed["url"]
    assert client.get(path).status_code == 404


# --- scans --------------------------------------------------------------------------


def test_start_scan_queues_one_task_per_category():
    resp = _client().post(
        "/api/opportunities/scans", json={"categories": ["student", "startup"], "focus": "agritech"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tasks"] == 2

    async def tasks():
        async with SessionLocal() as session:
            run = await session.get(Run, body["run_id"])
            rows = (
                await session.execute(
                    select(ResearchTask).where(ResearchTask.run_id == body["run_id"])
                )
            ).scalars().all()
            return run, sorted((t.task_type, t.target_name) for t in rows)

    run, rows = asyncio.run(tasks())
    assert run.region == settings.opportunity_default_region
    assert run.field == "Opportunities: startup, student"
    assert rows == [
        ("discover_opportunities", "category:startup"),
        ("discover_opportunities", "category:student"),
    ]


def test_task_brief_lists_known_titles_and_today():
    _add(title="Known Grant")
    message = opp_tasks.user_message(
        region="Ghana",
        category="startup",
        focus="climate",
        today="2026-11-07",
        known=["Known Grant (Accra Ventures)"],
    )
    assert "Today's date: 2026-11-07" in message
    assert "- Known Grant (Accra Ventures)" in message
    assert "climate" in message


def test_scheduled_sweep_runs_once_per_interval(monkeypatch):
    async def sweep():
        async with SessionLocal() as session:
            return await scans.maybe_sweep(session)

    async def age_earlier_scans():
        async with SessionLocal() as session:
            await session.execute(
                update(Run)
                .where(Run.field.like(f"{scans.SCAN_FIELD}:%"))
                .values(created_at=func.localtimestamp() - timedelta(days=30))
            )
            await session.commit()

    asyncio.run(age_earlier_scans())
    assert asyncio.run(sweep()) is None  # off by default
    monkeypatch.setattr(settings, "opportunity_sweep_email", TEST_USER_EMAIL)
    monkeypatch.setattr(settings, "opportunity_sweep_hours", 24)
    first = asyncio.run(sweep())
    assert first is not None
    assert asyncio.run(sweep()) is None


# --- the agent loop, end to end with a scripted model --------------------------------


class ScriptedScout:
    """Reads one page, saves what it says, then summarizes."""

    URL = "https://fund.example.org/call"

    def __init__(self):
        self.turn = 0

    async def chat(self, messages, system, tools, max_tokens=4096):
        from api.agent.llm.base import LLMResponse, ToolCall

        self.turn += 1
        names = {t["name"] for t in tools}
        assert {"fetch_page", "save_opportunity"} <= names
        if self.turn == 1:
            return LLMResponse(
                text="", tool_calls=[ToolCall(id="f1", name="fetch_page", arguments={"url": self.URL})]
            )
        if self.turn == 2:
            return LLMResponse(
                text="",
                tool_calls=[
                    ToolCall(
                        id="s1",
                        name="save_opportunity",
                        arguments={
                            "title": "Kumasi Innovation Fund",
                            "organization": "Example Fund",
                            "category": "startup",
                            "kind": "grant",
                            "summary": "Grants for Ghanaian hardware startups.",
                            "deadline": "2027-04-30",
                            "requirements": ["Pitch deck"],
                            "source_url": self.URL,
                        },
                    )
                ],
            )
        return LLMResponse(text="Saved 1 opportunity: Kumasi Innovation Fund.", tool_calls=[])


def test_discovery_task_saves_a_grounded_opportunity(monkeypatch):
    from api.agent import orchestrator as orch
    from api.prospects import web
    from api.runs import queue
    from api.runs.models import TaskStatus

    async def fake_fetch(url, max_chars=None, offset=0):
        return "Example Fund presents the Kumasi Innovation Fund. Deadline: 30 April 2027."

    monkeypatch.setattr(web, "fetch_page", fake_fetch)
    model = ScriptedScout()
    monkeypatch.setattr(orch, "get_provider", lambda **_: model)

    run_id = _client().post("/api/opportunities/scans", json={"categories": ["startup"]}).json()["run_id"]

    async def process():
        async with SessionLocal() as session:
            task = (
                await session.execute(select(ResearchTask).where(ResearchTask.run_id == run_id))
            ).scalar_one()
            task.status = TaskStatus.running
            await session.commit()
            await queue._process_claimed(session, task)
        async with SessionLocal() as session:
            task = (
                await session.execute(select(ResearchTask).where(ResearchTask.run_id == run_id))
            ).scalar_one()
            saved = (
                await session.execute(select(Opportunity).where(Opportunity.run_id == run_id))
            ).scalars().all()
            return task, saved

    task, saved = asyncio.run(process())
    assert task.status == TaskStatus.done, task.error
    assert "Kumasi Innovation Fund" in (task.final_text or "")
    assert [(o.title, o.deadline_date, o.status) for o in saved] == [
        ("Kumasi Innovation Fund", date(2027, 4, 30), "published")
    ]
