import asyncio
import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from api.core.db import SessionLocal
from api.main import app
from api.runs import models as run_models
from api.runs import service as run_service
from tests.conftest import TEST_USER_ID


def _client():
    return TestClient(app)


def _seed_run(client):
    resp = client.post(
        "/api/runs/from-list",
        json={
            "degree_level": "phd",
            "interest_statement": "robots",
            "programs": [
                {"school_name": "Live University", "program_name": "PhD in Live"}
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _collect_until_ping(run_id):
    async def drive():
        gen = run_service.run_events(run_id, TEST_USER_ID, poll_interval=0.01)
        try:
            frames = []
            for _ in range(20):
                frame = await gen.__anext__()
                frames.append(frame)
                if frame.startswith(": ping"):
                    break
            return frames
        finally:
            await gen.aclose()

    return asyncio.run(drive())


def test_task_frames_carry_board_shape():
    run_id = _seed_run(_client())
    frames = _collect_until_ping(run_id)

    task_frames = [f for f in frames if f.startswith("event: task")]
    assert task_frames, frames
    for frame in task_frames:
        _, _, data = frame.partition("data: ")
        payload = json.loads(data)
        assert set(payload) == {
            "id",
            "task_type",
            "target_name",
            "status",
            "turns",
            "error",
        }, payload


def test_error_change_reemits_task_frame():
    run_id = _seed_run(_client())

    async def drive():
        gen = run_service.run_events(run_id, TEST_USER_ID, poll_interval=0.01)
        try:
            frames = []
            for _ in range(20):
                frame = await gen.__anext__()
                frames.append(frame)
                if frame.startswith(": ping"):
                    break
            task_frames = [f for f in frames if f.startswith("event: task")]
            assert task_frames, frames
            _, _, data = task_frames[0].partition("data: ")
            task_id = json.loads(data)["id"]

            async with SessionLocal() as session:
                task = (
                    await session.execute(
                        select(run_models.ResearchTask).where(
                            run_models.ResearchTask.id == task_id
                        )
                    )
                ).scalar_one()
                task.error = "boom"
                await session.commit()

            frame = await gen.__anext__()
            assert frame.startswith("event: task"), frame
            _, _, data = frame.partition("data: ")
            payload = json.loads(data)
            assert payload["id"] == task_id
            assert payload["error"] == "boom"
        finally:
            await gen.aclose()

    asyncio.run(drive())
