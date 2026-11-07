import asyncio

import pytest
from fastapi.testclient import TestClient

from api.agent.llm.base import LLMResponse
from api.agent.orchestrator import run_agent_task
from api.agent.tools.context import ToolContext
from api.core.db import SessionLocal
from api.flows.service import FlowError
from api.main import app
from api.runs.models import Run

RUN = {
    "region": "X",
    "field": "y",
    "degree_level": "phd",
    "interest_statement": "robots",
}


class Recorder:
    name = "recorder"
    model = "r"

    def __init__(self):
        self.calls = []

    async def chat(self, messages, system, tools, max_tokens=4096):
        self.calls.append({"system": system, "tools": sorted(t["name"] for t in tools)})
        return LLMResponse(text="Done.", tool_calls=[], usage={})


def _custom_flow(client):
    flow = client.post(
        "/api/flows", json={"source": "standard", "name": "Scholar-only"}
    ).json()
    steps = flow["steps"]
    for s in steps:
        if s["type"] == "draft_email":
            s["enabled"] = False
        if s["type"] == "research_one_professor":
            s["tool_groups"] = ["scholar"]
            s["tools"] = ["score_alignment", "save_professor_record"]
            s["instructions"] = "Only consider authors with 3+ papers since 2020."
    r = client.patch(f"/api/flows/{flow['id']}", json={"steps": steps})
    assert r.status_code == 200, r.text
    return r.json()


def test_list_duplicate_and_validate():
    with TestClient(app) as client:
        listed = client.get("/api/flows").json()
        assert (
            listed["flows"][0]["id"] == "standard"
            and listed["flows"][0]["builtin"] is True
        )
        assert [s["type"] for s in listed["steps"]] == [
            "discover_programs",
            "research_professor",
            "research_one_professor",
            "draft_email",
        ]
        assert (
            client.patch("/api/flows/standard", json={"name": "x"}).status_code == 404
        )
        flow = _custom_flow(client)
        copy = client.post(
            "/api/flows", json={"source": flow["id"], "name": "Copy"}
        ).json()
        assert copy["steps"] == flow["steps"]
        bad = [
            [{"type": "nope"}],
            [{"type": "research_one_professor", "tools": ["send_email_now"]}],
            [{"type": "research_one_professor", "tool_groups": ["root"]}],
            [{"type": "research_one_professor", "instructions": "x" * 1501}],
            [
                {"type": "research_professor", "enabled": False},
                {"type": "research_one_professor", "enabled": False},
            ],
        ]
        for steps in bad:
            assert (
                client.patch(
                    f"/api/flows/{flow['id']}", json={"steps": steps}
                ).status_code
                == 400
            )


def test_custom_flow_runs_end_to_end_with_guardrails(monkeypatch):
    import api.agent.orchestrator as orch

    recorder = Recorder()
    monkeypatch.setattr(orch, "get_provider", lambda **_: recorder)
    with TestClient(app) as client:
        flow = _custom_flow(client)
        run = client.post("/api/runs", json={**RUN, "flow_id": flow["id"]}).json()
        assert run["flow_id"] == flow["id"]
        assert (
            client.post(
                "/api/runs", json={**RUN, "flow_id": "someone-elses"}
            ).status_code
            == 404
        )
        client.patch(
            "/api/agent/tools/worker/get_author_works", json={"enabled": False}
        )

    async def go(task_type):
        async with SessionLocal() as session:
            row = await session.get(Run, run["id"])
            return await run_agent_task(
                "BASE PROMPT",
                "do it",
                ToolContext(session=session, run=row),
                task_type=task_type,
            )

    result = asyncio.run(go("research_one_professor"))
    assert result["final_text"]
    [call] = recorder.calls
    # Narrowed to the flow's tools AND the account's enabled tools, never more.
    assert call["tools"] == [
        "find_openalex_author",
        "save_professor_record",
        "score_alignment",
    ]
    assert call["system"].startswith("BASE PROMPT")
    assert "Only consider authors with 3+ papers" in call["system"]

    skipped = asyncio.run(go("draft_email"))
    assert skipped["final_text"].startswith("Skipped:") and len(recorder.calls) == 1

    asyncio.run(go("research_professor"))
    assert "spawn_professor_research" in recorder.calls[-1]["tools"]

    with TestClient(app) as client:
        for tool in (
            "find_openalex_author",
            "score_alignment",
            "save_professor_record",
        ):
            client.patch(f"/api/agent/tools/worker/{tool}", json={"enabled": False})
    with pytest.raises(FlowError, match="allows no tools"):
        asyncio.run(go("research_one_professor"))
    with TestClient(app) as client:
        for tool in (
            "find_openalex_author",
            "score_alignment",
            "save_professor_record",
            "get_author_works",
        ):
            client.patch(f"/api/agent/tools/worker/{tool}", json={"enabled": True})


def test_deleting_a_flow_falls_back_to_standard():
    with TestClient(app) as client:
        flow = _custom_flow(client)
        run = client.post("/api/runs", json={**RUN, "flow_id": flow["id"]}).json()
        assert client.delete(f"/api/flows/{flow['id']}").status_code == 200
        assert client.get(f"/api/runs/{run['id']}").json()["flow_id"] is None
