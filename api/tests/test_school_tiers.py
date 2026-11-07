import asyncio
from collections import Counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from api.agent.tools import ToolContext, dispatch
from api.core.config import settings
from api.core.db import SessionLocal
from api.main import app
from api.prospects import tasks as prospect_tasks
from api.prospects import tiers
from api.prospects.models import RunSchool
from api.runs.models import Run
from tests.conftest import TEST_USER_ID


@pytest.fixture(autouse=True)
def _roomy_task_budget(monkeypatch):
    monkeypatch.setattr(settings, "max_programs_per_task", 50)


def _run(school_tiers: list[str] | None, max_programs: int) -> str:
    async def go():
        async with SessionLocal() as session:
            run = Run(
                user_id=TEST_USER_ID,
                region="Canada",
                field="computer vision",
                degree_level="phd",
                interest_statement="3D reconstruction",
                status="running",
                max_programs=max_programs,
                school_tiers=tiers.dump(school_tiers),
            )
            session.add(run)
            await session.commit()
            return run.id

    return asyncio.run(go())


def _save_all(run_id: str, saves: list[tuple[str, str | None]]) -> list[dict]:
    async def go():
        async with SessionLocal() as session:
            ctx = ToolContext(session=session, run=await session.get(Run, run_id))
            out = []
            for n, (name, tier) in enumerate(saves):
                body = {"school_name": name, "program_name": f"PhD {n}"}
                if tier is not None:
                    body["school_tier"] = tier
                out.append(await dispatch("save_program", body, ctx))
            return out

    return asyncio.run(go())


def _tiers_saved(run_id: str) -> Counter:
    async def go():
        async with SessionLocal() as session:
            rows = await session.execute(
                select(RunSchool.tier).where(RunSchool.run_id == run_id)
            )
            return Counter(t for (t,) in rows.all())

    return asyncio.run(go())


def test_run_stores_its_tiers():
    client = TestClient(app)
    body = {
        "region": "Canada",
        "field": "vision",
        "degree_level": "phd",
        "interest_statement": "I study 3D reconstruction from images and video.",
        "school_tiers": ["solid", "top", "solid"],
    }
    res = client.post("/api/runs", json=body)
    assert res.status_code == 200, res.text
    run = res.json()
    assert run["school_tiers"] == ["top", "solid"]  # canonical order, deduped
    assert client.get(f"/api/runs/{run['id']}").json()["school_tiers"] == [
        "top",
        "solid",
    ]
    assert (
        client.post("/api/runs", json={**body, "school_tiers": ["elite"]}).status_code
        == 422
    )
    plain = client.post(
        "/api/runs", json={k: v for k, v in body.items() if k != "school_tiers"}
    )
    assert plain.json()["school_tiers"] == []


def test_discovery_brief_names_the_tiers_and_their_share(monkeypatch):
    run_id = _run(["top", "solid"], max_programs=10)
    seen = {}

    async def fake_agent(system_prompt, user_message, ctx, **kwargs):
        seen["brief"] = user_message
        return {"final_text": "", "tool_log": [], "turns": 0, "usage": {}}

    monkeypatch.setattr(prospect_tasks, "run_agent_task", fake_agent)

    async def go():
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            await prospect_tasks.run_discover_programs(session, None, run)

    asyncio.run(go())
    brief = seen["brief"]
    assert "- top:" in brief and "- solid:" in brief
    assert "- strong:" not in brief
    assert "at most 5 schools per tier" in brief
    assert "school_tier" in brief


def test_multi_tier_selection_is_balanced():
    run_id = _run(["top", "strong", "solid"], max_programs=6)
    saves = [
        ("Toronto", "top"),
        ("UBC", "top"),
        ("McGill", "top"),  # third top school: over the top tier's share
        ("Waterloo", "strong"),
        ("Alberta", "strong"),
        ("Calgary", "solid"),
        ("Ottawa", "solid"),
        ("Laval", "strong"),  # strong is full too
    ]
    results = _save_all(run_id, saves)
    refused = {saves[i][0]: r["error"] for i, r in enumerate(results) if "error" in r}
    assert set(refused) == {"McGill", "Laval"}
    assert "share" in refused["McGill"] and "strong, solid" in refused["McGill"]
    assert _tiers_saved(run_id) == Counter({"top": 2, "strong": 2, "solid": 2})


def test_tier_outside_the_selection_or_missing_is_refused():
    run_id = _run(["solid", "accessible"], max_programs=4)
    results = _save_all(run_id, [("Toronto", "top"), ("Nowhere", None)])
    assert all("targets solid, accessible" in r["error"] for r in results)
    assert _tiers_saved(run_id) == Counter()


def test_single_tier_gets_the_whole_cap():
    run_id = _run(["accessible"], max_programs=4)
    saves = [(f"Regional {n}", "accessible") for n in range(5)]
    results = _save_all(run_id, saves)
    assert all("program_id" in r for r in results[:4])
    assert "budget reached" in results[4]["error"]  # the run cap, not a tier share
    assert _tiers_saved(run_id) == Counter({"accessible": 4})


def test_runs_without_tiers_are_unchanged(monkeypatch):
    run_id = _run(None, max_programs=3)
    results = _save_all(run_id, [("Toronto", None), ("UBC", "top")])
    assert all("program_id" in r for r in results)
    assert _tiers_saved(run_id) == Counter({None: 2})


def test_school_listing_shows_the_tier():
    run_id = _run(["strong"], max_programs=2)
    _save_all(run_id, [("Waterloo", "strong")])
    listed = TestClient(app).get(f"/api/runs/{run_id}/programs").json()
    assert [(s["name"], s["tier"]) for s in listed] == [("Waterloo", "strong")]
