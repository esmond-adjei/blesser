import asyncio
import json
import uuid

import pytest
from sqlalchemy import select

from api.agent.llm.anthropic_provider import AnthropicProvider
from api.core.db import SessionLocal
from api.prospects import rosters, web
from api.prospects import tasks as prospect_tasks
from api.prospects.models import FacultyRoster, Program
from api.prospects.prompts import (
    INDEX_APPLICATION_SYSTEM_PROMPT,
    ROSTER_EXTRACTION_SYSTEM_PROMPT,
)
from api.runs.models import ResearchTask, Run
from tests.conftest import TEST_USER_ID
from tests.test_budgets import _make_program, _make_run

pytestmark = pytest.mark.rosters
NAMES = ["Ada Lovelace", "Grace Hopper", "Alan Turing", "Barbara Liskov"]


@pytest.mark.parametrize(
    ("reply", "names"),
    [
        ('["Ada Lovelace", "Grace Hopper"]', ["Ada Lovelace", "Grace Hopper"]),
        ('Here they are:\n[{"name": "Ada  Lovelace"}, {"name": "Grace Hopper"}]', ["Ada Lovelace", "Grace Hopper"]),
        ('["Ada Lovelace", "Ada Lovelace", "Faculty", "42 Main St", ""]', ["Ada Lovelace"]),
        ("[]", []),
        ("no list", []),
        ("[not json", []),
    ],
)
def test_the_extraction_reply_becomes_names(reply, names):
    assert rosters.parse_names(reply) == names


def test_rosters_are_keyed_by_the_department_page():
    assert rosters.roster_key("https://WWW.cs.Uni.edu/People/?x=1") == "cs.uni.edu/people"
    assert rosters.roster_key(None) is None and rosters.roster_key("not a url") is None
    assert rosters.listing_urls("https://cs.uni.edu/grad/") == [
        "https://cs.uni.edu/grad/",
        "https://cs.uni.edu/grad/people",
        "https://cs.uni.edu/grad/faculty",
    ]


def _supervisor(monkeypatch, *, pages=None, extraction=None, agent=None, seed=None):
    """Run one supervisor task on a fresh programme; returns (result, lead names, (system, message) calls)."""
    run_id = _make_run()
    _, program_id = _make_program(run_id)
    url = f"https://cs{uuid.uuid4().hex[:6]}.uni.example/faculty-list"
    calls = []

    async def fetch(page_url, max_chars=3000, offset=0):
        return (pages if pages is not None else {}).get(page_url, "[Could not fetch: 404]")

    async def model(system_prompt, user_message, ctx, **kwargs):
        calls.append((system_prompt, user_message))
        if system_prompt == INDEX_APPLICATION_SYSTEM_PROMPT:
            return {"final_text": "", "tool_log": [], "turns": 0, "usage": {}}
        if system_prompt == ROSTER_EXTRACTION_SYSTEM_PROMPT:
            return {"final_text": extraction(user_message), "turns": 1, "usage": {"input_tokens": 100, "output_tokens": 20}}
        return await agent(ctx) if agent else {"final_text": "nothing", "tool_log": [], "turns": 3, "usage": {}}

    async def no_seed(institution_id, interest, limit):
        return seed or []

    monkeypatch.setattr(web, "fetch_page", fetch)
    monkeypatch.setattr(prospect_tasks, "run_agent_task", model)
    monkeypatch.setattr(rosters, "openalex_seed", no_seed)

    async def go():
        async with SessionLocal() as session:
            program = await session.get(Program, program_id)
            program.department_url = url
            task = ResearchTask(user_id=TEST_USER_ID, run_id=run_id, task_type="research_professor", target_id=program_id)
            session.add(task)
            await session.commit()
            run = await session.get(Run, run_id)
            out = await prospect_tasks.run_research_professor(session, task, run)
            leads = (
                await session.execute(
                    select(ResearchTask.target_name)
                    .where(ResearchTask.run_id == run_id, ResearchTask.task_type == "research_one_professor")
                    .order_by(ResearchTask.created_at)
                )
            ).scalars().all()
            return out, sorted(leads), url

    out, leads, url = asyncio.run(go())
    return out, leads, calls, url


def _stored(url):
    async def read():
        async with SessionLocal() as session:
            row = await session.get(FacultyRoster, rosters.roster_key(url))
            return (json.loads(row.names), row.source) if row else None

    return asyncio.run(read())


def test_the_page_path_needs_no_agent_loop(monkeypatch):
    seen = {}

    def extraction(message):
        seen["message"] = message
        return json.dumps(NAMES)

    class Pages(dict):
        def get(self, key, default=None):
            return "Faculty: Ada Lovelace, Grace Hopper, Alan Turing, Barbara Liskov" if key.endswith("faculty-list") else default

    out, leads, calls, url = _supervisor(monkeypatch, pages=Pages(), extraction=extraction)
    assert [c[0] for c in calls] == [ROSTER_EXTRACTION_SYSTEM_PROMPT, INDEX_APPLICATION_SYSTEM_PROMPT]
    assert leads == sorted(NAMES)
    assert out["turns"] == 1 and out["usage"] == {"input_tokens": 100, "output_tokens": 20}
    assert "Queued 4 of 4 faculty names" in out["final_text"]
    assert _stored(url) == (NAMES, "page")


def test_a_stored_roster_only_calls_the_admissions_model(monkeypatch):
    class Pages(dict):
        def get(self, key, default=None):
            return "Faculty page" if key.endswith("faculty-list") else default

    _, _, _, url = _supervisor(monkeypatch, pages=Pages(), extraction=lambda m: json.dumps(NAMES))

    run_id = _make_run()
    _, program_id = _make_program(run_id)

    async def no_model(prompt, *args, **kwargs):
        assert prompt == INDEX_APPLICATION_SYSTEM_PROMPT
        return {"final_text": "", "tool_log": [], "turns": 0, "usage": {}}

    monkeypatch.setattr(prospect_tasks, "run_agent_task", no_model)

    async def go():
        async with SessionLocal() as session:
            program = await session.get(Program, program_id)
            program.department_url = url
            task = ResearchTask(user_id=TEST_USER_ID, run_id=run_id, task_type="research_professor", target_id=program_id)
            session.add(task)
            await session.commit()
            return await prospect_tasks.run_research_professor(session, task, await session.get(Run, run_id))

    out = asyncio.run(go())
    assert "from a stored faculty list" in out["final_text"] and out["turns"] == 0


def test_too_few_names_hand_over_to_the_agent_and_its_list_is_kept(monkeypatch):
    from api.agent.tools import dispatch

    async def agent(ctx):
        result = await dispatch("spawn_professor_research", {"names": NAMES[:3]}, ctx)
        return {
            "final_text": "queued",
            "tool_log": [{"tool": "spawn_professor_research", "input": {"names": NAMES[:3]}, "result": result}],
            "turns": 6,
            "usage": {},
        }

    class Pages(dict):
        def get(self, key, default=None):
            return "A page with one name" if key.endswith(("faculty-list", "/people")) else default

    _, leads, calls, url = _supervisor(monkeypatch, pages=Pages(), extraction=lambda m: '["Ada Lovelace"]', agent=agent)
    assert [c[0] == ROSTER_EXTRACTION_SYSTEM_PROMPT for c in calls] == [True, True, False, False]
    assert calls[-1][0] == INDEX_APPLICATION_SYSTEM_PROMPT
    assert leads == sorted(NAMES[:3])
    assert _stored(url) == (NAMES[:3], "agent")


def test_openalex_seeds_a_programme_whose_faculty_page_cannot_be_read(monkeypatch):
    out, leads, calls, url = _supervisor(monkeypatch, pages={}, extraction=lambda m: "[]", seed=["Ada Lovelace", "Grace Hopper"])
    assert [c[0] == ROSTER_EXTRACTION_SYSTEM_PROMPT for c in calls] == [False, False]
    assert calls[-1][0] == INDEX_APPLICATION_SYSTEM_PROMPT
    assert leads == ["Ada Lovelace", "Grace Hopper"]
    assert "authors OpenAlex places at the school" in out["final_text"]
    assert _stored(url) is None  # a seed isn't a faculty list


def test_the_seed_keeps_current_authors_publishing_on_the_topic(monkeypatch):
    from api.prospects import openalex

    async def topical(institution_id, query, years=5, limit=200):
        return [
            {"openalex_id": "A1", "name": "Ada Lovelace", "works": 5},
            {"openalex_id": "A2", "name": "Old Coauthor", "works": 4},  # not at the school now
            {"openalex_id": "A3", "name": "One Paper", "works": 1},  # too little on the topic
        ]

    async def current(institution_id):
        return [{"id": "https://openalex.org/A1"}, {"id": "https://openalex.org/A3"}]

    monkeypatch.setattr(openalex, "authors_publishing_on", topical)
    monkeypatch.setattr(openalex, "school_authors", current)
    names = asyncio.run(rosters.openalex_seed("I1", "legged robots on rough terrain", 5))
    assert names == ["Ada Lovelace"]
    assert asyncio.run(rosters.openalex_seed(None, "robots", 5)) == []


def test_a_tool_less_call_sends_no_tools():
    provider = AnthropicProvider(api_key="k", model="claude-x")
    assert "tools" not in provider._prompt("Read the page.", [])
    assert "tools" in provider._prompt("Research.", [{"name": "t", "description": "d", "parameters": {"type": "object", "properties": {}}}])
