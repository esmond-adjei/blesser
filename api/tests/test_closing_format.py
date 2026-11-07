import asyncio

from tests.conftest import TEST_USER_ID


def test_with_closing_format_appends_the_labels_once_in_order():
    from api.agent.orchestrator import CLOSING_FORMAT_BLOCK, with_closing_format

    out = with_closing_format("Research this program")
    assert out.startswith("Research this program")
    assert CLOSING_FORMAT_BLOCK in out
    idx = [out.index(label) for label in ("Findings:", "Saved:", "Skipped:", "Next:")]
    assert idx == sorted(idx)
    assert with_closing_format(out) == out


def test_fresh_brief_carries_closing_format(monkeypatch):
    import api.agent.orchestrator as orch
    from api.agent.llm.base import LLMResponse

    seen = []

    class StubProvider:
        async def chat(self, messages, system, tools, max_tokens=4096):
            seen.append(list(messages))
            return LLMResponse(text="done", tool_calls=[])

    monkeypatch.setattr(orch, "get_provider", lambda: StubProvider())
    async def _run():
        from api.agent.tools.context import ToolContext
        from api.core.db import SessionLocal
        from api.runs.models import Run

        async with SessionLocal() as session:
            run = await session.get(Run, "run-closing-fresh")
            if run is None:
                run = Run(user_id=TEST_USER_ID, 
                    id="run-closing-fresh",
                    region="United States",
                    field="robotics",
                    degree_level="phd",
                    interest_statement="robots",
                    status="running",
                )
                session.add(run)
                await session.commit()
            return await orch.run_agent_task(
                "sys", "fresh brief", ctx=ToolContext(session=session, run=run)
            )

    out = asyncio.run(_run())
    assert out["final_text"] == "done"
    assert len(seen) == 1
    assert seen[0][0]["role"] == "user"
    content = seen[0][0]["content"]
    assert content.startswith("fresh brief")
    for label in ("Findings:", "Saved:", "Skipped:", "Next:"):
        assert label in content


def test_resume_path_skips_closing_format(monkeypatch):
    import api.agent.orchestrator as orch
    from api.agent.llm.base import LLMResponse

    seen = []

    class StubProvider:
        async def chat(self, messages, system, tools, max_tokens=4096):
            seen.append(list(messages))
            return LLMResponse(text="resumed", tool_calls=[])

    monkeypatch.setattr(orch, "get_provider", lambda: StubProvider())
    resume = [
        {"role": "user", "content": "original brief without block"},
        {"role": "assistant", "content": "partial work"},
    ]
    async def _run_resume():
        from api.agent.tools.context import ToolContext
        from api.core.db import SessionLocal
        from api.runs.models import Run

        async with SessionLocal() as session:
            run = await session.get(Run, "run-closing-resume")
            if run is None:
                run = Run(user_id=TEST_USER_ID, 
                    id="run-closing-resume",
                    region="United States",
                    field="robotics",
                    degree_level="phd",
                    interest_statement="robots",
                    status="running",
                )
                session.add(run)
                await session.commit()
            return await orch.run_agent_task(
                "sys",
                "fresh brief",
                ctx=ToolContext(session=session, run=run),
                resume_messages=resume,
            )

    out = asyncio.run(_run_resume())
    assert out["final_text"] == "resumed"
    assert seen[0] == resume
    assert "Findings:" not in seen[0][0]["content"]
