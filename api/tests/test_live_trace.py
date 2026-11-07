"""`turns` is only written when a task concludes, so progress reaches the feed as `trace` frames."""

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
            "interest_statement": "trace robots",
            "programs": [
                {"school_name": "Trace University", "program_name": "PhD in Trace"}
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _frames_of(frames, event):
    """Frames for exactly one event name (`task` must not catch `trace`)."""
    out = []
    for frame in frames:
        head, _, data = frame.partition("\n")
        if head == f"event: {event}":
            out.append(json.loads(data.partition("data: ")[2]))
    return out


async def _drain_to_ping(gen, limit=40):
    frames = []
    for _ in range(limit):
        frame = await gen.__anext__()
        frames.append(frame)
        if frame.startswith(": ping"):
            break
    return frames


async def _set_running_with_log(run_id, entries):
    """Put the run's task in `running` with a trace, as the worker does."""
    async with SessionLocal() as session:
        task = (
            await session.execute(
                select(run_models.ResearchTask).where(
                    run_models.ResearchTask.run_id == run_id
                )
            )
        ).scalars().first()
        assert task is not None
        task.status = run_models.TaskStatus.running
        task.log = json.dumps(entries)
        await session.commit()
        return task.id


def _entry(turn):
    return {
        "turn": turn,
        "tool": "search_web",
        "input": {"query": f"q{turn}"},
        "result_preview": "{}",
        "ok": True,
        "note": "",
    }


def test_growing_trace_emits_delta_frames():
    run_id = _seed_run(_client())

    async def drive():
        task_id = await _set_running_with_log(run_id, [_entry(1)])
        gen = run_service.run_events(run_id, TEST_USER_ID, poll_interval=0.01)
        try:
            first = await _drain_to_ping(gen)
            traces = _frames_of(first, "trace")
            assert traces, first
            assert traces[0]["id"] == task_id
            # First sight of a running task sends the whole trace, so the client replaces it.
            assert traces[0]["from"] == 0
            assert [e["turn"] for e in traces[0]["events"]] == [1]

            async with SessionLocal() as session:
                task = await session.get(run_models.ResearchTask, task_id)
                assert task is not None
                task.log = json.dumps([_entry(1), _entry(2)])
                await session.commit()

            second = await _drain_to_ping(gen)
            deltas = _frames_of(second, "trace")
            assert deltas, second
            assert deltas[0]["from"] == 1
            assert deltas[0]["total"] == 2
            assert [e["turn"] for e in deltas[0]["events"]] == [2]
        finally:
            await gen.aclose()

    asyncio.run(drive())


def test_task_frames_never_carry_trace_keys():
    run_id = _seed_run(_client())

    async def drive():
        await _set_running_with_log(run_id, [_entry(1)])
        gen = run_service.run_events(run_id, TEST_USER_ID, poll_interval=0.01)
        try:
            frames = await _drain_to_ping(gen)
            for payload in _frames_of(frames, "task"):
                assert set(payload) == {
                    "id",
                    "task_type",
                    "target_name",
                    "status",
                    "turns",
                    "error",
                }, payload
        finally:
            await gen.aclose()

    asyncio.run(drive())


def test_concluded_task_stops_streaming_trace():
    """Streaming a finished task's trace would resend the whole log every sweep."""
    run_id = _seed_run(_client())

    async def drive():
        task_id = await _set_running_with_log(run_id, [_entry(1)])
        gen = run_service.run_events(run_id, TEST_USER_ID, poll_interval=0.01)
        try:
            await _drain_to_ping(gen)
            async with SessionLocal() as session:
                task = await session.get(run_models.ResearchTask, task_id)
                assert task is not None
                task.status = run_models.TaskStatus.done
                task.turns = 2
                task.log = json.dumps([_entry(1), _entry(2)])
                await session.commit()
            frames = await _drain_to_ping(gen)
            assert _frames_of(frames, "trace") == []
            assert [p["status"] for p in _frames_of(frames, "task")] == ["done"]
        finally:
            await gen.aclose()

    asyncio.run(drive())


def test_feed_survives_a_drained_queue():
    """`done` is data about the queue, not the end of the stream."""
    run_id = _seed_run(_client())

    async def drive():
        async with SessionLocal() as session:
            task = (
                await session.execute(
                    select(run_models.ResearchTask).where(
                        run_models.ResearchTask.run_id == run_id
                    )
                )
            ).scalars().first()
            assert task is not None
            task.status = run_models.TaskStatus.done
            await session.commit()

        gen = run_service.run_events(run_id, TEST_USER_ID, poll_interval=0.01)
        try:
            frames = await _drain_to_ping(gen)
            assert _frames_of(frames, "done"), frames

            # The generator is still alive, so this reaches the client without a reconnect.
            async with SessionLocal() as session:
                session.add(
                    run_models.ResearchTask(user_id=TEST_USER_ID, 
                        run_id=run_id, task_type="research_professor"
                    )
                )
                await session.commit()

            for _ in range(10):
                frames = await _drain_to_ping(gen)
                pending = [
                    p for p in _frames_of(frames, "task") if p["status"] == "pending"
                ]
                if pending:
                    break
            else:  # pragma: no cover - diagnostic
                raise AssertionError("queued task never pushed after done")
        finally:
            await gen.aclose()

    asyncio.run(drive())


def test_run_status_change_pushes_a_frame():
    """Pausing a run changes no task row, so it needs its own frame."""
    client = _client()
    run_id = _seed_run(client)

    async def drive():
        gen = run_service.run_events(run_id, TEST_USER_ID, poll_interval=0.01)
        try:
            first = await _drain_to_ping(gen)
            assert [p["status"] for p in _frames_of(first, "run_status")] == ["running"]

            assert client.post(f"/api/runs/{run_id}/pause").status_code == 200

            for _ in range(10):
                frames = await _drain_to_ping(gen)
                statuses = [p["status"] for p in _frames_of(frames, "run_status")]
                if "paused" in statuses:
                    break
            else:  # pragma: no cover - diagnostic
                raise AssertionError("pause never pushed a run_status frame")
        finally:
            await gen.aclose()

    asyncio.run(drive())
