"""The agent loop and dispatcher: nudges, resumes, concurrency, ordering and failures."""

import asyncio
import json

import pytest

from api.agent import orchestrator as orch
from api.agent.llm.base import LLMResponse, ToolCall
from api.agent.tools import dispatch as dispatch_module
from api.agent.tools.dispatch import HANDLERS, READ_ONLY_TOOLS, dispatch_batch


def _scripted(script, seen):
    """Script entries are ("final", text) or ("call", tool_name, args); records messages seen."""
    calls = {"n": 0}

    class Stub:
        async def chat(self, messages, system, tools, max_tokens=4096):
            seen.append(json.loads(json.dumps(messages, default=str)))
            step = script[calls["n"]]
            calls["n"] += 1
            if step[0] == "final":
                return LLMResponse(text=step[1], tool_calls=[])
            return LLMResponse(text="", tool_calls=[ToolCall(id=f"t{calls['n']}", name=step[1], arguments=step[2])])

    return Stub()


class _Ctx:
    """No session or run: the halt check is skipped."""

    def __init__(self):
        self.offered_tools = None
        self.failed_calls = {}


def _run_task(monkeypatch, script, **kwargs):
    seen: list = []
    monkeypatch.setattr(orch, "get_provider", lambda **_: _scripted(script, seen))

    async def fake_batch(calls, ctx):
        return [{"ok": True} for _ in calls]

    monkeypatch.setattr(orch, "dispatch_batch", fake_batch)
    result = asyncio.run(orch.run_agent_task("sys", "go", _Ctx(), **kwargs))  # type: ignore[arg-type]
    return result, seen


def test_empty_finish_is_nudged_back_to_work(monkeypatch):
    result, seen = _run_task(
        monkeypatch,
        [("final", "done already"), ("call", "save_opportunity", {}), ("final", "saved one")],
        progress_tools={"save_opportunity"},
    )
    assert result["nudges"] == 1
    assert result["final_text"] == "saved one"
    assert orch.EMPTY_FINISH_NUDGE in json.dumps(seen[1])


def test_nudges_are_bounded(monkeypatch):
    monkeypatch.setattr(orch.settings, "max_empty_finish_nudges", 2)
    result, _ = _run_task(
        monkeypatch, [("final", "a"), ("final", "b"), ("final", "c")], progress_tools={"save_opportunity"}
    )
    assert result["nudges"] == 2 and result["final_text"] == "c"


def test_no_nudge_without_progress_tools(monkeypatch):
    result, _ = _run_task(monkeypatch, [("final", "nothing to do")])
    assert result["nudges"] == 0


def test_resume_counts_prior_saves_and_turns(monkeypatch):
    history = [
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "t1", "name": "save_opportunity", "arguments": {}}]},
        {"role": "tool", "tool_call_id": "t1", "name": "save_opportunity", "content": "{}"},
    ]
    result, _ = _run_task(
        monkeypatch, [("final", "wrapped up")], resume_messages=history, progress_tools={"save_opportunity"}
    )
    assert result["nudges"] == 0 and result["turns"] == 2


def test_closing_format_is_asked_for_once():
    once = orch.with_closing_format("brief")
    assert orch.with_closing_format(once) == once
    assert "Saved:" in once and "Skipped:" in once


# --- dispatcher -------------------------------------------------------------------

SLEEP = 0.05


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


@pytest.fixture
def ctx():
    return _Ctx()


def test_reads_overlap_and_results_keep_request_order(monkeypatch, ctx):
    order: list[str] = []
    _install(monkeypatch, order)
    calls = [("fetch_page", {"url": f"https://e.example/{i}"}) for i in range(4)]

    async def go():
        loop = asyncio.get_running_loop()
        started = loop.time()
        results = await dispatch_batch(calls, ctx)
        return results, loop.time() - started

    results, elapsed = asyncio.run(go())
    assert elapsed < SLEEP * 3
    assert [r["echo"]["url"] for r in results] == [c[1]["url"] for c in calls]


def test_a_write_waits_for_the_reads_before_it(monkeypatch, ctx):
    order: list[str] = []
    _install(monkeypatch, order)
    calls = [("fetch_page", {"url": "https://e.example/a"}), ("save_opportunity", {"title": "x"})]
    asyncio.run(dispatch_batch(calls, ctx))
    assert order == ["fetch_page", "save_opportunity"]


def test_one_failing_tool_does_not_sink_its_siblings(monkeypatch, ctx):
    async def boom(tool_input, ctx):
        raise RuntimeError("network down")

    async def fine(tool_input, ctx):
        return {"results": []}

    monkeypatch.setitem(HANDLERS, "fetch_page", boom)
    monkeypatch.setitem(HANDLERS, "search_web", fine)
    results = asyncio.run(
        dispatch_batch([("fetch_page", {"url": "https://x.example"}), ("search_web", {"query": "q"})], ctx)
    )
    assert results[0]["error"].startswith("fetch_page failed: network down")
    assert results[1] == {"results": []}
    # The same failing read isn't sent again in this task.
    again = asyncio.run(dispatch_batch([("fetch_page", {"url": "https://x.example"})], ctx))
    assert "already failed" in again[0]["error"]


def test_tools_not_offered_are_refused(monkeypatch, ctx):
    ctx.offered_tools = {"search_web"}
    results = asyncio.run(dispatch_batch([("save_opportunity", {"title": "x"})], ctx))
    assert "not available" in results[0]["error"]


def test_halted_task_refuses_every_tool(monkeypatch):
    class Run:
        status = "running"

    class Halted(_Ctx):
        session = object()
        run = Run()

    async def halted(ctx):
        return "cancelled"

    monkeypatch.setattr(dispatch_module, "run_halted", halted)
    results = asyncio.run(dispatch_batch([("search_web", {"query": "q"})], Halted()))
    assert "halted" in results[0]["error"]
