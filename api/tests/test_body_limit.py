import asyncio

import pytest
from fastapi.testclient import TestClient

from api.core.body_limit import BodySizeLimitMiddleware
from api.main import app

pytestmark = pytest.mark.real_auth  # no session: the limit must come first


def _drive(mw, headers, chunks):
    """Run the middleware against a recording inner app."""
    reads = {"n": 0}
    called = {"app": False}
    sent = []

    async def inner(scope, receive, send):
        called["app"] = True
        while True:
            msg = await receive()
            if not msg.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    queue = list(chunks)

    async def receive():
        reads["n"] += 1
        body = queue.pop(0) if queue else b""
        return {"type": "http.request", "body": body, "more_body": bool(queue)}

    async def send(msg):
        sent.append(msg)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/opportunities",
        "headers": headers,
    }
    asyncio.run(BodySizeLimitMiddleware(inner, **mw)(scope, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    return status, reads["n"], called["app"]


def test_declared_oversize_is_refused_without_reading_the_body():
    status, reads, called = _drive(
        {"default_limit": 1000},
        [(b"content-length", str(50 * 1024 * 1024).encode())],
        [b"x" * 1024] * 10,
    )
    assert status == 413 and reads == 0 and called is False


def test_undeclared_oversize_is_cut_off_at_the_limit():
    status, reads, _ = _drive({"default_limit": 3000}, [], [b"x" * 1024] * 50)
    assert status == 413
    assert reads <= 4  # stopped right after crossing 3000 bytes, not all 50


def test_unauthenticated_50mb_body_gets_413():
    with TestClient(app) as client:
        resp = client.post(
            "/api/opportunities",
            content=b"x" * (50 * 1024 * 1024),
            headers={"content-type": "multipart/form-data; boundary=x"},
        )
    assert resp.status_code == 413


def test_large_json_body_is_refused():
    with TestClient(app) as client:
        resp = client.post(
            "/api/auth/login",
            content=b'{"email": "' + b"a" * (3 * 1024 * 1024) + b'"}',
            headers={"content-type": "application/json"},
        )
    assert resp.status_code == 413
