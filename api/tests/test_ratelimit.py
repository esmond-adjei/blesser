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
    monkeypatch.setitem(ratelimit.LIMITS, "scan", [(2, 60)])
    with TestClient(app) as client:
        body = {"categories": ["startup"]}
        assert client.post("/api/scans", json=body).status_code == 200
        assert client.post("/api/scans", json=body).status_code == 200
        blocked = client.post("/api/scans", json=body)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    assert "Too many scans" in blocked.json()["detail"]
