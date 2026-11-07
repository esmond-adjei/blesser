from fastapi.testclient import TestClient

from api.main import app


def _client():
    return TestClient(app)


def _seed_run(client):
    resp = client.post(
        "/api/runs/from-list",
        json={
            "degree_level": "phd",
            "interest_statement": "robots",
            "programs": [
                {"school_name": "Seed University", "program_name": "PhD in Seed"}
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def test_create_school_without_programs_stays_bare():
    client = _client()
    run_id = _seed_run(client)
    before = client.get(f"/api/runs/{run_id}/tasks").json()
    before_count = len(before)

    resp = client.post(
        f"/api/runs/{run_id}/schools",
        json={"name": "Manual University", "country": "Nowhere"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Manual University"
    assert body["programs"] == []

    after = client.get(f"/api/runs/{run_id}/tasks").json()
    assert len(after) == before_count


def test_create_school_with_inline_programs_queues_research():
    client = _client()
    run_id = _seed_run(client)

    resp = client.post(
        f"/api/runs/{run_id}/schools",
        json={
            "name": "Inline University",
            "country": "Somewhere",
            "programs": [
                {"name": "PhD in Inline"},
                {
                    "name": "MS in Inline",
                    "department_url": "https://example.edu/inline-ms",
                },
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Inline University"
    assert len(body["programs"]) == 2
    names = {p["name"] for p in body["programs"]}
    assert names == {"PhD in Inline", "MS in Inline"}
    ms = next(p for p in body["programs"] if p["name"] == "MS in Inline")
    assert ms["department_url"] == "https://example.edu/inline-ms"
    assert all(p["professors"] == 0 for p in body["programs"])
    program_ids = {p["id"] for p in body["programs"]}

    tasks = client.get(f"/api/runs/{run_id}/tasks").json()
    queued = {
        t["target_id"]
        for t in tasks
        if t["task_type"] == "research_professor" and t["target_id"] in program_ids
    }
    assert queued == program_ids

    fetched = client.get(f"/api/schools/{body['id']}").json()
    assert {p["name"] for p in fetched["programs"]} == names


def test_create_school_with_empty_programs_list_stays_bare():
    client = _client()
    run_id = _seed_run(client)
    before = len(client.get(f"/api/runs/{run_id}/tasks").json())

    resp = client.post(
        f"/api/runs/{run_id}/schools",
        json={"name": "Empty Programs University", "programs": []},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["programs"] == []
    assert len(client.get(f"/api/runs/{run_id}/tasks").json()) == before


def test_create_school_with_programs_unknown_run_404():
    client = _client()
    resp = client.post(
        "/api/runs/does-not-exist/schools",
        json={"name": "Ghost University", "programs": [{"name": "PhD in Ghost"}]},
    )
    assert resp.status_code == 404


def test_create_school_program_entry_requires_name():
    client = _client()
    run_id = _seed_run(client)
    resp = client.post(
        f"/api/runs/{run_id}/schools",
        json={
            "name": "Bad University",
            "programs": [{"department_url": "https://x.edu"}],
        },
    )
    assert resp.status_code == 422
