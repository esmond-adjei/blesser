import asyncio
import time

import pytest

from api.agent.tools.dispatch import HANDLERS, READ_ONLY_TOOLS, dispatch_batch


class _FakeRun:
    status = "running"


class _FakeSession:
    """Stands in for AsyncSession and records concurrent entry."""

    def __init__(self):
        self.refreshes = 0
        self.inside = 0
        self.max_inside = 0

    async def refresh(self, _obj, attribute_names=None):
        self.refreshes += 1
        self.inside += 1
        self.max_inside = max(self.max_inside, self.inside)
        await asyncio.sleep(0)
        self.inside -= 1


class _FakeCtx:
    def __init__(self):
        self.session = _FakeSession()
        self.run = _FakeRun()


SLEEP = 0.05


@pytest.fixture
def ctx():
    return _FakeCtx()


def _install(monkeypatch, order):
    """Replace every handler with a recorder; reads sleep, writes don't."""

    def make(name):
        async def handler(tool_input, ctx):
            if name in READ_ONLY_TOOLS:
                await asyncio.sleep(SLEEP)
            order.append(name)
            return {"tool": name, "echo": tool_input}

        return handler

    for name in list(HANDLERS):
        monkeypatch.setitem(HANDLERS, name, make(name))


def test_read_only_calls_overlap(monkeypatch, ctx):
    _install(monkeypatch, [])
    calls = [("fetch_page", {"url": f"https://example.test/{i}"}) for i in range(5)]

    started = time.perf_counter()
    results = asyncio.run(dispatch_batch(calls, ctx))
    elapsed = time.perf_counter() - started

    assert len(results) == 5
    # Serial would be 5 * SLEEP; half of that still fails if the overlap is gone.
    assert elapsed < SLEEP * 5 * 0.5, elapsed


def test_results_follow_request_order(monkeypatch, ctx):
    _install(monkeypatch, [])
    calls = [("fetch_page", {"url": f"https://example.test/{i}"}) for i in range(5)]
    results = asyncio.run(dispatch_batch(calls, ctx))
    # Completion order isn't request order; the trace and replayed history are built off this list.
    assert [r["echo"]["url"] for r in results] == [
        f"https://example.test/{i}" for i in range(5)
    ]


def test_writes_stay_serial_and_ordered(monkeypatch, ctx):
    order: list[str] = []
    _install(monkeypatch, order)
    calls = [
        ("fetch_page", {"url": "https://example.test/a"}),
        ("save_program", {"school_name": "S", "program_name": "P"}),
        ("fetch_page", {"url": "https://example.test/b"}),
        ("save_professor_record", {"name": "N"}),
    ]
    results = asyncio.run(dispatch_batch(calls, ctx))

    assert [r["tool"] for r in results] == [
        "fetch_page",
        "save_program",
        "fetch_page",
        "save_professor_record",
    ]
    assert order.index("save_program") > order.index("fetch_page")
    assert order[-1] == "save_professor_record"


def test_halt_check_runs_once_per_turn(monkeypatch, ctx):
    _install(monkeypatch, [])
    calls = [("fetch_page", {"url": f"https://example.test/{i}"}) for i in range(6)]
    asyncio.run(dispatch_batch(calls, ctx))
    assert ctx.session.refreshes == 1
    assert ctx.session.max_inside == 1


def test_halted_run_refuses_work_but_allows_confirm(monkeypatch):
    _install(monkeypatch, [])
    ctx = _FakeCtx()
    ctx.run.status = "cancelled"
    results = asyncio.run(
        dispatch_batch(
            [
                ("fetch_page", {"url": "https://example.test/a"}),
                ("save_program", {"school_name": "S", "program_name": "P"}),
                ("confirm_no_match", {"reason": "nobody fits"}),
            ],
            ctx,
        )
    )
    assert "cancelled" in results[0]["error"]
    assert "cancelled" in results[1]["error"]
    # Refusing confirm_no_match would strand a halted task with nothing to say.
    assert results[2]["tool"] == "confirm_no_match"


def test_one_failing_tool_does_not_sink_its_siblings(monkeypatch, ctx):
    async def boom(tool_input, ctx):
        raise RuntimeError("403 from a university server")

    async def ok(tool_input, ctx):
        await asyncio.sleep(SLEEP)
        return {"tool": "fetch_page", "echo": tool_input}

    monkeypatch.setitem(HANDLERS, "search_web", boom)
    monkeypatch.setitem(HANDLERS, "fetch_page", ok)

    results = asyncio.run(
        dispatch_batch(
            [
                ("search_web", {"query": "x"}),
                ("fetch_page", {"url": "https://example.test/a"}),
            ],
            ctx,
        )
    )
    assert "403" in results[0]["error"]
    assert results[1]["echo"]["url"] == "https://example.test/a"
