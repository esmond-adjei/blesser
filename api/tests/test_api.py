from fastapi.testclient import TestClient

from tests.conftest import TEST_USER_ID


def _client():
    from api.main import app

    return TestClient(app)


def test_run_lifecycle_without_worker():
    with _client() as client:
        created = client.post(
            "/api/runs",
            json={
                "region": "United States",
                "field": "robotics",
                "degree_level": "phd",
                "interest_statement": "Mobile robotics and RL for indoor navigation.",
            },
        )
        assert created.status_code == 200, created.text
        run_id = created.json()["id"]

        got = client.get(f"/api/runs/{run_id}")
        assert got.status_code == 200

        candidates = client.get(f"/api/runs/{run_id}/candidates")
        assert candidates.status_code == 200
        assert candidates.json() == []

        missing = client.post("/api/candidates/does-not-exist/request-draft")
        assert missing.status_code == 404


def test_orchestrator_runs_with_stub_provider(monkeypatch):
    import api.agent.orchestrator as orch
    from api.agent.llm.base import LLMResponse, ToolCall

    calls = {"n": 0}

    class StubProvider:
        async def chat(self, messages, system, tools, max_tokens=4096):
            calls["n"] += 1
            if calls["n"] == 1:
                return LLMResponse(
                    text="",
                    tool_calls=[
                        ToolCall(
                            id="t1",
                            name="score_alignment",
                            arguments={
                                "interest_text": "robotics",
                                "abstracts": ["robotics nav"],
                            },
                        )
                    ],
                )
            return LLMResponse(text="done", tool_calls=[])

    monkeypatch.setattr(orch, "get_provider", lambda: StubProvider())

    # dispatch_batch takes [(name, arguments)] and returns results in request order.
    async def fake_dispatch(calls, ctx, task_type=None):
        assert [name for name, _ in calls] == ["score_alignment"]
        return [{"score": 0.9, "best_index": 0, "all_scores": [0.9]} for _ in calls]

    monkeypatch.setattr(orch, "dispatch_batch", fake_dispatch)

    import asyncio

    async def _run():
        from api.agent.tools.context import ToolContext
        from api.core.db import SessionLocal
        from api.runs.models import Run

        async with SessionLocal() as session:
            run = await session.get(Run, "run-orch-stub")
            if run is None:
                run = Run(user_id=TEST_USER_ID, 
                    id="run-orch-stub",
                    region="United States",
                    field="robotics",
                    degree_level="phd",
                    interest_statement="robots",
                    status="running",
                )
                session.add(run)
                await session.commit()
            return await orch.run_agent_task(
                "sys", "hello", ctx=ToolContext(session=session, run=run)
            )

    out = asyncio.run(_run())
    assert out["final_text"] == "done"
    assert out["turns"] == 2
    assert out["tool_log"][0]["tool"] == "score_alignment"
