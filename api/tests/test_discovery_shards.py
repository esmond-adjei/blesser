import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select

from api.core.db import SessionLocal
from api.main import app
from api.prospects import tasks as prospect_tasks
from api.runs.models import ResearchTask, Run


def _create(**body):
    resp = TestClient(app).post(
        "/api/runs",
        json={
            "region": "Canada",
            "field": "robotics",
            "degree_level": "phd",
            "interest_statement": "robot learning for manipulation",
            "max_programs": 10,
            **body,
        },
    )
    assert resp.status_code in (200, 201), resp.text
    run_id = resp.json()["id"]

    async def tasks():
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(ResearchTask).where(ResearchTask.run_id == run_id).order_by(ResearchTask.created_at)
                )
            ).scalars().all()
            return run_id, [(t.task_type, t.target_name) for t in rows]

    return asyncio.run(tasks())


def test_three_tiers_start_three_discovery_shards():
    _, tasks = _create(school_tiers=["top", "strong", "solid"])
    assert tasks == [
        ("discover_programs", "tier:top"),
        ("discover_programs", "tier:strong"),
        ("discover_programs", "tier:solid"),
    ]


def test_regions_shard_only_between_two_and_four():
    _, two = _create(region="Canada, United States")
    assert [name for _, name in two] == ["region:Canada", "region:United States"]
    _, anywhere = _create(region="Anywhere")
    assert [name for _, name in anywhere] == [None]
    _, many = _create(region="Canada, United States, Germany, France, Japan")
    assert [name for _, name in many] == [None]


def test_a_shard_is_briefed_for_its_part_and_share(monkeypatch):
    run_id, _ = _create(school_tiers=["top", "strong", "solid"])
    seen = {}

    async def fake_agent(system_prompt, user_message, ctx, **kwargs):
        seen["message"] = user_message
        return {"final_text": "ok", "tool_log": [], "turns": 1, "usage": {}, "nudges": 0}

    monkeypatch.setattr(prospect_tasks, "run_agent_task", fake_agent)

    async def go():
        async with SessionLocal() as session:
            task = (
                await session.execute(
                    select(ResearchTask).where(
                        ResearchTask.run_id == run_id, ResearchTask.target_name == "tier:strong"
                    )
                )
            ).scalar_one()
            run = await session.get(Run, run_id)
            await prospect_tasks.run_discover_programs(session, task, run)

    asyncio.run(go())
    message = seen["message"]
    assert "Only save schools in the strong tier." in message
    assert "this one covers only strong and may save at most 4 programs" in message  # ceil(10/3)
    assert "save at most 4 programs in this task" in message
    assert "- strong:" in message and "- top:" not in message and "- solid:" not in message
