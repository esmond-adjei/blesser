"""Every domain endpoint is scoped to the caller: foreign ids 404, never 401, so ownership looks like absence."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from api.core.db import SessionLocal
from api.main import app
from api.runs import models as run_models

pytestmark = pytest.mark.real_auth

PASSWORD = "correct-horse-99"


def _client():
    return TestClient(app)


def _register(client, email: str) -> dict:
    resp = client.post(
        "/api/auth/register", json={"accept_terms": True, "email": email, "password": PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _headers(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _account(client, email: str) -> dict:
    return _headers(_register(client, email)["tokens"])


def _make_run(client, headers: dict) -> dict:
    resp = client.post(
        "/api/runs",
        json={
            "region": "Canada",
            "field": "robotics",
            "degree_level": "phd",
            "interest_statement": "mobile manipulation for warehouse logistics",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_cross_account_runs_invisible():
    client = _client()
    alice = _account(client, "alice@example.com")
    bob = _account(client, "bob@example.com")
    run = _make_run(client, alice)

    assert client.get("/api/runs", headers=bob).json() == []
    assert client.get(f"/api/runs/{run['id']}", headers=bob).status_code == 404
    assert (
        client.patch(
            f"/api/runs/{run['id']}", json={"max_programs": 3}, headers=bob
        ).status_code
        == 404
    )
    assert client.get(f"/api/runs/{run['id']}/usage", headers=bob).status_code == 404
    assert client.get(f"/api/runs/{run['id']}/board", headers=bob).status_code == 404
    assert client.delete(f"/api/runs/{run['id']}", headers=bob).status_code == 404
    assert client.get(f"/api/runs/{run['id']}/events", headers=bob).status_code == 404
    assert client.get(f"/api/runs/{run['id']}/events").status_code == 401
    assert client.get(f"/api/runs/{run['id']}", headers=alice).status_code == 200
    assert len(client.get("/api/runs", headers=alice).json()) == 1


def test_cross_account_subtree_invisible():
    client = _client()
    alice = _account(client, "alice2@example.com")
    bob = _account(client, "bob2@example.com")
    seeded = client.post(
        "/api/runs/from-list",
        json={
            "degree_level": "phd",
            "interest_statement": "perception for humanoids",
            "programs": [
                {"school_name": "Iso University", "program_name": "PhD in Robotics"}
            ],
        },
        headers=alice,
    )
    assert seeded.status_code == 200, seeded.text
    run_id = seeded.json()["id"]

    tree = client.get(f"/api/runs/{run_id}/programs", headers=alice).json()
    school_id = tree[0]["id"]
    program_id = tree[0]["programs"][0]["id"]
    tasks = client.get(f"/api/runs/{run_id}/tasks", headers=alice).json()
    task_id = tasks[0]["id"]

    for path in (
        f"/schools/{school_id}",
        f"/programs/{program_id}",
        f"/tasks/{task_id}",
        f"/runs/{run_id}/programs",
        f"/runs/{run_id}/tasks",
    ):
        assert client.get(path, headers=bob).status_code == 404, path
    # Writes into a foreign parent are refused, not scoped elsewhere.
    assert (
        client.post(
            f"/schools/{school_id}/programs",
            json={"name": "Sneaky PhD"},
            headers=bob,
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/programs/{program_id}", json={"name": "Sneaky"}, headers=bob
        ).status_code
        == 404
    )


def test_registries_seed_per_account():
    client = _client()
    alice = _account(client, "alice3@example.com")
    bob = _account(client, "bob3@example.com")

    patched = client.patch(
        "/api/providers/ollama",
        json={"model": "qwen3:8b", "api_key": "alice-key", "is_active": True},
        headers=alice,
    )
    assert patched.status_code == 200, patched.text

    bob_rows = {r["provider"]: r for r in client.get("/api/providers", headers=bob).json()}
    assert bob_rows["ollama"]["has_key"] is False
    assert bob_rows["ollama"]["is_active"] is False

    disabled = client.patch(
        "/api/agent/tools/worker/fetch_page", json={"enabled": False}, headers=alice
    )
    assert disabled.status_code == 200, disabled.text
    bob_tools = {
        (t["scope"], t["name"]): t
        for t in client.get("/api/agent/tools", headers=bob).json()
    }
    assert bob_tools[("worker", "fetch_page")]["enabled"] is True


def test_applications_conversations_and_health_are_scoped():
    client = _client()
    alice = _account(client, "alice4@example.com")
    bob = _account(client, "bob4@example.com")

    app = client.post(
        "/api/applications",
        json={"school": "Iso University", "program": "PhD in Robotics"},
        headers=alice,
    )
    assert app.status_code == 200, app.text
    app_id = app.json()["id"]
    conv = client.post("/api/assistant/conversations", headers=alice)
    assert conv.status_code == 200, conv.text
    conv_id = conv.json()["id"]
    _make_run(client, alice)

    assert client.get("/api/applications", headers=bob).json() == []
    assert client.get(f"/api/applications/{app_id}", headers=bob).status_code == 404
    assert client.get("/api/assistant/conversations", headers=bob).json() == []
    assert (
        client.get(f"/api/assistant/conversations/{conv_id}", headers=bob).status_code
        == 404
    )

    alice_health = client.get("/health", headers=alice).json()
    assert alice_health["database"]["runs"] == 1
    bob_health = client.get("/health", headers=bob).json()
    assert bob_health["database"]["runs"] == 0
    assert client.get("/health").status_code == 401


def test_delete_account_removes_owned_rows():
    import asyncio

    client = _client()
    created = _register(client, "doomed@example.com")
    headers = _headers(created["tokens"])
    run = _make_run(client, headers)

    deleted = client.request(
        "DELETE", "/api/auth/account", json={"password": PASSWORD}, headers=headers
    )
    assert deleted.status_code == 200, deleted.text

    async def _rows():
        async with SessionLocal() as session:
            return (
                await session.execute(
                    select(func.count())
                    .select_from(run_models.Run)
                    .where(run_models.Run.id == run["id"])
                )
            ).scalar()

    assert asyncio.run(_rows()) == 0
