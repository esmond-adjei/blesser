import pytest
from fastapi.testclient import TestClient

from api.core import ratelimit
from api.core.ratelimit import RateLimiter
from api.main import app


def test_limiter_windows_and_isolation(monkeypatch):
    monkeypatch.setitem(ratelimit.LIMITS, "chat", [(2, 60), (3, 3600)])
    rl = RateLimiter()
    assert rl.hit("chat", "a", now=0) is None
    assert rl.hit("chat", "a", now=1) is None
    wait = rl.hit("chat", "a", now=2)
    assert wait is not None and 57 <= wait <= 59  # burst window
    assert rl.hit("chat", "b", now=2) is None
    assert rl.hit("chat", "a", now=61) is None
    hourly = rl.hit("chat", "a", now=122)
    assert hourly is not None and hourly > 3000  # sustained window holds


@pytest.mark.rate_limits
def test_endpoint_returns_429_with_retry_after(monkeypatch):
    monkeypatch.setitem(ratelimit.LIMITS, "agent_work", [(2, 60)])
    with TestClient(app) as client:
        body = {
            "region": "X",
            "field": "y",
            "degree_level": "phd",
            "interest_statement": "robots",
        }
        assert client.post("/api/runs", json=body).status_code == 200
        assert client.post("/api/runs", json=body).status_code == 200
        blocked = client.post("/api/runs", json=body)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    assert "Too many research requests" in blocked.json()["detail"]


@pytest.mark.real_auth
def test_delete_account_purges_cv_files(tmp_path, monkeypatch):
    import uuid
    from pathlib import Path

    from api.core.config import settings
    from tests.cv_fixtures import corpus_simple

    monkeypatch.setattr(settings, "cv_storage_dir", str(tmp_path / "cv_storage"))
    with TestClient(app) as client:
        email = f"purge-{uuid.uuid4().hex[:8]}@example.com"
        password = "long-enough-pw-1"
        reg = client.post(
            "/api/auth/register", json={"accept_terms": True, "email": email, "password": password}
        )
        headers = {"Authorization": f"Bearer {reg.json()['tokens']['access_token']}"}
        doc = client.post(
            "/api/cv/documents",
            headers=headers,
            files={"file": ("cv.docx", corpus_simple(), "application/octet-stream")},
            data={"title": "CV"},
        )
        assert doc.status_code == 200, doc.text
        folder = Path(settings.cv_storage_dir) / "cv" / doc.json()["id"]
        assert folder.exists() and any(folder.rglob("*"))
        gone = client.request(
            "DELETE", "/api/auth/account", headers=headers, json={"password": password}
        )
        assert gone.status_code == 200, gone.text
    assert not folder.exists()
