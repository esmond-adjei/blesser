import asyncio

from fastapi.testclient import TestClient

from api.core.db import SessionLocal
from api.main import app
from api.runs.models import ResearchTask, TaskStatus
from tests.conftest import TEST_USER_ID


def _client():
    return TestClient(app)


def _seed_run(client):
    resp = client.post(
        "/api/runs/from-list",
        json={
            "degree_level": "phd",
            "interest_statement": "board robots",
            "programs": [
                {
                    "school_name": "Board University",
                    "program_name": "PhD in Board Robotics",
                },
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _add_task(run_id, **kwargs):
    async def setup():
        async with SessionLocal() as session:
            task = ResearchTask(user_id=TEST_USER_ID, run_id=run_id, **kwargs)
            session.add(task)
            await session.commit()
            return task.id

    return asyncio.run(setup())


def test_board_groups_slim_tasks_without_trace_payloads():
    client = _client()
    run_id = _seed_run(client)
    seeded = client.get(f"/api/runs/{run_id}/tasks").json()
    assert len(seeded) == 1
    seeded_id = seeded[0]["id"]

    _add_task(
        run_id,
        task_type="research_professor",
        status=TaskStatus.running,
        target_name="Prof Runner",
        turns=3,
    )
    _add_task(
        run_id,
        task_type="draft_email",
        status=TaskStatus.done,
        target_name="Prof Done",
        turns=5,
        log='[{"turn": 1, "tool": "search_web"}]',
        final_text="finished summary",
        messages_json='[{"role": "user", "content": "go"}]',
        input_tokens=100,
        output_tokens=50,
        target_id="prof-123",
    )
    _add_task(
        run_id,
        task_type="research_one_professor",
        status=TaskStatus.error,
        target_name="Prof Broken",
        error="boom",
        turns=2,
        log='[{"turn": 1, "tool": "fetch_page"}]',
        final_text="failed summary",
    )

    resp = client.get(f"/api/runs/{run_id}/board")
    assert resp.status_code == 200, resp.text
    board = resp.json()
    assert set(board) == {
        "pending", "running", "done", "error", "paused", "cancelled", "deferred",
    }  # fmt: skip

    slim_keys = {"id", "task_type", "target_name", "status", "turns", "error", "updated_at"}
    for column in board.values():
        for card in column:
            assert set(card) == slim_keys, card

    assert {c["id"] for c in board["pending"]} == {seeded_id}
    assert board["pending"][0]["task_type"] == "research_professor"

    (running,) = board["running"]
    assert running["target_name"] == "Prof Runner"
    assert running["turns"] == 3
    assert running["error"] is None

    (done,) = board["done"]
    assert done["target_name"] == "Prof Done"
    assert done["turns"] == 5
    assert done["status"] == "done"

    (failed,) = board["error"]
    assert failed["error"] == "boom"
    assert failed["target_name"] == "Prof Broken"


def test_board_returns_waiting_leads():
    client = _client()
    run_id = _seed_run(client)
    _add_task(
        run_id,
        task_type="research_one_professor",
        status=TaskStatus.deferred,
        target_name="Prof Waiting",
    )
    board = client.get(f"/api/runs/{run_id}/board").json()
    assert [c["target_name"] for c in board["deferred"]] == ["Prof Waiting"]
    assert board["deferred"][0]["status"] == "deferred"


def test_board_missing_run_is_404():
    client = _client()
    assert client.get("/api/runs/does-not-exist/board").status_code == 404


def test_board_route_is_tagged_tasks():
    tags = app.openapi()["paths"]["/api/runs/{run_id}/board"]["get"]["tags"]
    assert tags == ["tasks"]
