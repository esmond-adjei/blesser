import asyncio
import json


def _scripted_stub(script, seen):
    """Script entries are ("final", text) or ("call", tool_name, args); records messages seen."""
    from api.agent.llm.base import LLMResponse, ToolCall

    calls = {"n": 0}

    class StubProvider:
        async def chat(self, messages, system, tools, max_tokens=4096):
            seen.append(json.loads(json.dumps(messages, default=str)))
            kind = script[calls["n"]]
            calls["n"] += 1
            if kind[0] == "final":
                return LLMResponse(text=kind[1], tool_calls=[])
            return LLMResponse(
                text="",
                tool_calls=[
                    ToolCall(id=f"t{calls['n']}", name=kind[1], arguments=kind[2])
                ],
            )

    return StubProvider()


def test_nudge_on_empty_finish(monkeypatch):
    import api.agent.orchestrator as orch

    seen = []
    stub = _scripted_stub(
        [
            ("final", "quitting early"),
            ("call", "save_program", {}),
            ("final", "done properly"),
        ],
        seen,
    )
    monkeypatch.setattr(orch, "get_provider", lambda: stub)

    # dispatch_batch is the seam: it takes [(name, arguments)] and returns results in request order.
    async def fake_dispatch(calls, ctx, task_type=None):
        return [{"program_id": "p1"} for _ in calls]

    monkeypatch.setattr(orch, "dispatch_batch", fake_dispatch)

    out = asyncio.run(
        orch.run_agent_task("sys", "go", ctx=object(), progress_tools={"save_program"})  # type: ignore[arg-type]
    )
    assert out["final_text"] == "done properly"
    assert out["nudges"] == 1
    assert len(seen) == 3
    assert seen[1][-1]["role"] == "user"
    assert "without saving anything" in seen[1][-1]["content"]


def test_nudge_bounded(monkeypatch):
    import api.agent.orchestrator as orch
    from api.core.config import settings

    monkeypatch.setattr(settings, "max_empty_finish_nudges", 1)
    seen = []
    stub = _scripted_stub([("final", "nope"), ("final", "still nope")], seen)
    monkeypatch.setattr(orch, "get_provider", lambda: stub)

    out = asyncio.run(
        orch.run_agent_task("sys", "go", ctx=object(), progress_tools={"save_program"})  # type: ignore[arg-type]
    )
    assert out["final_text"] == "still nope"
    assert out["nudges"] == 1
    assert len(seen) == 2


def test_no_nudge_when_progress_made(monkeypatch):
    import api.agent.orchestrator as orch

    seen = []
    stub = _scripted_stub([("call", "save_program", {}), ("final", "saved one")], seen)
    monkeypatch.setattr(orch, "get_provider", lambda: stub)

    async def fake_dispatch(calls, ctx, task_type=None):
        return [{"program_id": "p1"} for _ in calls]

    monkeypatch.setattr(orch, "dispatch_batch", fake_dispatch)

    out = asyncio.run(
        orch.run_agent_task("sys", "go", ctx=object(), progress_tools={"save_program"})  # type: ignore[arg-type]
    )
    assert out["final_text"] == "saved one"
    assert out["nudges"] == 0
    assert len(seen) == 2


def test_no_nudge_without_progress_tools(monkeypatch):
    import api.agent.orchestrator as orch

    seen = []
    stub = _scripted_stub([("final", "immediate")], seen)
    monkeypatch.setattr(orch, "get_provider", lambda: stub)

    out = asyncio.run(orch.run_agent_task("sys", "go", ctx=object()))  # type: ignore[arg-type]
    assert out["final_text"] == "immediate"
    assert out["nudges"] == 0
    assert len(seen) == 1


def test_resume_counts_prior_saves_as_progress(monkeypatch):
    import api.agent.orchestrator as orch

    seen = []
    stub = _scripted_stub([("final", "wrapping up")], seen)
    monkeypatch.setattr(orch, "get_provider", lambda: stub)

    resume = [
        {"role": "user", "content": "go"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "t1", "name": "save_program", "arguments": {}}],
        },
        {"role": "tool", "tool_call_id": "t1", "name": "save_program", "content": "{}"},
    ]
    out = asyncio.run(
        orch.run_agent_task(
            "sys",
            "go",
            ctx=object(),  # type: ignore[arg-type]
            resume_messages=resume,
            progress_tools={"save_program"},
        )
    )
    assert out["final_text"] == "wrapping up"
    assert out["nudges"] == 0
    assert len(seen) == 1


def test_confirm_no_match_counts_as_progress(monkeypatch):
    import api.agent.orchestrator as orch

    seen = []
    stub = _scripted_stub(
        [
            ("call", "confirm_no_match", {"reason": "weak alignment"}),
            ("final", "no fit"),
        ],
        seen,
    )
    monkeypatch.setattr(orch, "get_provider", lambda: stub)

    async def fake_dispatch(calls, ctx, task_type=None):
        assert [name for name, _ in calls] == ["confirm_no_match"]
        return [{"acknowledged": True} for _ in calls]

    monkeypatch.setattr(orch, "dispatch_batch", fake_dispatch)

    out = asyncio.run(
        orch.run_agent_task(
            "sys",
            "go",
            ctx=object(),  # type: ignore[arg-type]
            progress_tools={"save_professor_record", "confirm_no_match"},
        )
    )
    assert out["final_text"] == "no fit"
    assert out["nudges"] == 0
    assert len(seen) == 2


def test_confirm_no_match_dispatch_is_noop():
    import asyncio as _asyncio

    from api.agent.tools import dispatch

    out = _asyncio.run(dispatch("confirm_no_match", {"reason": "x"}, ctx=object()))  # type: ignore[arg-type]
    assert out == {"acknowledged": True, "reason": "x", "reason_code": "other"}
