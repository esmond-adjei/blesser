"""The wake rides on a dedicated `work` section, since `tasks` also fires on every tool-call progress write."""

import asyncio
import contextlib
import os
from urllib.parse import urlsplit, urlunsplit

import asyncpg
from fastapi.testclient import TestClient

from api.core.db import SessionLocal
from api.main import app
from api.runs import models as run_models
from api.runs.notify import CHANNEL, SECTIONS, notify_tasks, notify_work, parse_payload
from api.runs.queue import WorkSignal
from tests.conftest import TEST_USER_ID

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://graduator:graduator@localhost:5432/graduator_test",
)


def _dsn():
    parts = urlsplit(TEST_DATABASE_URL)
    return urlunsplit(("postgresql", parts.netloc, parts.path, "", ""))


@contextlib.asynccontextmanager
async def _listen():
    conn = await asyncpg.connect(_dsn())
    received: asyncio.Queue = asyncio.Queue()
    conn_cb = None

    def _cb(*args):
        received.put_nowait(args[3])

    conn_cb = _cb
    await conn.add_listener(CHANNEL, conn_cb)
    try:
        yield received
    finally:
        with contextlib.suppress(Exception):
            await conn.remove_listener(CHANNEL, conn_cb)
        await conn.close()


async def _sections_for(received, run_id, timeout=5.0):
    """Every section seen for this run until the queue goes quiet."""
    seen = []
    while True:
        try:
            payload = await asyncio.wait_for(received.get(), timeout=timeout)
        except TimeoutError:
            return seen
        parsed = parse_payload(payload)
        if parsed is not None and parsed[0] == run_id:
            seen.append(parsed[1])
            timeout = 0.5  # drain the rest of the burst, then stop


def test_work_is_a_distinct_section():
    assert "work" in SECTIONS
    assert parse_payload("run-1:work") == ("run-1", "work")
    # A bad wake is worse than a missed one, so nonsense must still be rejected.
    for section in ("tasks", "candidates", "drafts"):
        assert parse_payload(f"run-1:{section}") == ("run-1", section)
    assert parse_payload("run-1:bogus") is None


def test_enqueue_emits_work_and_progress_does_not():
    """A per-turn task notify must not wake the worker, or every tool call costs an idle claim query."""

    async def run():
        async with _listen() as received:
            run_id = TestClient(app).post(
                "/api/runs/from-list",
                json={
                    "degree_level": "phd",
                    "interest_statement": "wake robots",
                    "programs": [
                        {"school_name": "Wake University", "program_name": "PhD in Wake"}
                    ],
                },
            ).json()["id"]
            # Creating the run already emitted its enqueue; drain that.
            await _sections_for(received, run_id)

            async with SessionLocal() as session:
                await notify_tasks(session, run_id)
                await session.commit()
            assert "work" not in await _sections_for(received, run_id)

            async with SessionLocal() as session:
                await notify_work(session, run_id)
                await session.commit()
            assert "work" in await _sections_for(received, run_id)

    asyncio.run(run())


def test_enqueue_site_wakes_the_worker():
    async def run():
        async with _listen() as received:
            client = TestClient(app)
            run_id = client.post(
                "/api/runs/from-list",
                json={
                    "degree_level": "phd",
                    "interest_statement": "chain robots",
                    "programs": [
                        {
                            "school_name": "Chain University",
                            "program_name": "PhD in Chain",
                        }
                    ],
                },
            ).json()["id"]
            await _sections_for(received, run_id)

            async with SessionLocal() as session:
                from api.runs.lifecycle import note_work_enqueued

                session.add(
                    run_models.ResearchTask(user_id=TEST_USER_ID, 
                        run_id=run_id, task_type="research_professor"
                    )
                )
                await note_work_enqueued(session, run_id)
                await session.commit()

            sections = await _sections_for(received, run_id)
            assert "work" in sections, sections
            assert "tasks" in sections, sections

    asyncio.run(run())


def test_work_signal_fans_out_and_does_not_lose_a_wake():
    """A loop busy when the wake arrived still sees it on its next wait (the event stays set)."""

    async def run():
        signal = WorkSignal()
        a = signal.register()
        b = signal.register()

        signal.wake_all()
        await asyncio.wait_for(signal.wait(a, 1.0), timeout=2.0)
        await asyncio.wait_for(signal.wait(b, 1.0), timeout=2.0)
        assert not a.is_set()
        assert not b.is_set()

        started = asyncio.get_running_loop().time()
        await signal.wait(a, 0.2)
        assert asyncio.get_running_loop().time() - started >= 0.2

    asyncio.run(run())
