import uuid

import pytest
from fastapi.testclient import TestClient

from api.main import app

pytestmark = pytest.mark.real_auth


def _account(client) -> dict:
    resp = client.post(
        "/api/auth/register",
        json={"accept_terms": True, "email": f"paging-{uuid.uuid4().hex[:8]}@example.com", "password": "correct-horse-99"},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['tokens']['access_token']}"}


def _pages(client, path: str, headers: dict, size: int) -> list[list[str]]:
    pages, offset = [], 0
    while True:
        page = client.get(path, params={"limit": size, "offset": offset}, headers=headers)
        assert page.status_code == 200, page.text
        ids = [item["id"] for item in page.json()]
        pages.append(ids)
        if len(ids) < size:
            return pages
        offset += size


def test_chats_page_without_overlap():
    client = TestClient(app)
    headers = _account(client)
    for _ in range(5):
        assert client.post("/api/assistant/conversations", headers=headers).status_code == 200
    everything = [c["id"] for c in client.get("/api/assistant/conversations", headers=headers).json()]
    pages = _pages(client, "/api/assistant/conversations", headers, 2)
    assert [len(p) for p in pages] == [2, 2, 1]
    assert [i for p in pages for i in p] == everything
    assert client.get("/api/assistant/conversations", params={"limit": 0}, headers=headers).status_code == 422


def test_runs_page_without_overlap():
    client = TestClient(app)
    headers = _account(client)
    for _ in range(3):
        resp = client.post(
            "/api/runs",
            json={"region": "Canada", "field": "robotics", "degree_level": "phd",
                  "interest_statement": "mobile manipulation for warehouse logistics"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
    everything = [r["id"] for r in client.get("/api/runs", headers=headers).json()]
    assert len(everything) == 3
    pages = _pages(client, "/api/runs", headers, 2)
    assert [len(p) for p in pages] == [2, 1]
    assert [i for p in pages for i in p] == everything
