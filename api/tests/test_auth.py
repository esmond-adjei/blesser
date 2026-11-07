import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from api.auth import models as auth_models
from api.core.db import SessionLocal
from api.main import app

pytestmark = pytest.mark.real_auth


@pytest.fixture(autouse=True)
def _clean_auth():
    async def _wipe():
        async with SessionLocal() as session:
            await session.execute(delete(auth_models.RefreshToken))
            await session.execute(delete(auth_models.User))
            await session.commit()

    asyncio.run(_wipe())


def _client():
    return TestClient(app)


def _register(client, email="ada@example.edu", password="correct-horse-99"):
    resp = client.post(
        "/api/auth/register", json={"accept_terms": True, "email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_register_login_me_round_trip():
    client = _client()
    created = _register(client)
    assert created["user"]["email"] == "ada@example.edu"
    assert created["tokens"]["token_type"] == "bearer"

    me = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {created['tokens']['access_token']}"},
    )
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "ada@example.edu"

    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": "Bearer forged"}
        ).status_code
        == 401
    )


def test_login_rejects_bad_credentials():
    client = _client()
    _register(client, email="grace@example.edu")
    bad_password = client.post(
        "/api/auth/login",
        json={"email": "grace@example.edu", "password": "wrong-password-1"},
    )
    assert bad_password.status_code == 401
    unknown = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.edu", "password": "wrong-password-1"},
    )
    assert unknown.status_code == 401
    assert (
        "password" not in unknown.text.lower() or "wrong email" in unknown.text.lower()
    )


def test_register_rejects_duplicates_and_short_passwords():
    client = _client()
    _register(client, email="dup@example.edu")
    again = client.post(
        "/api/auth/register",
        json={"accept_terms": True, "email": "DUP@example.edu", "password": "correct-horse-99"},
    )
    assert again.status_code == 409
    short = client.post(
        "/api/auth/register", json={"accept_terms": True, "email": "new@example.edu", "password": "short"}
    )
    assert short.status_code == 422


def test_refresh_rotates_and_logout_revokes():
    client = _client()
    created = _register(client, email="refresh@example.edu")
    first_refresh = created["tokens"]["refresh_token"]

    rotated = client.post("/api/auth/refresh", json={"refresh_token": first_refresh})
    assert rotated.status_code == 200, rotated.text
    second_refresh = rotated.json()["tokens"]["refresh_token"]
    assert second_refresh != first_refresh

    replay = client.post("/api/auth/refresh", json={"refresh_token": first_refresh})
    assert replay.status_code == 401

    me = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {rotated.json()['tokens']['access_token']}"},
    )
    assert me.status_code == 200

    assert (
        client.post(
            "/api/auth/logout", json={"refresh_token": second_refresh}
        ).status_code
        == 200
    )
    spent = client.post("/api/auth/refresh", json={"refresh_token": second_refresh})
    assert spent.status_code == 401


def test_login_throttle_locks_out(monkeypatch):
    from api.core.config import settings

    monkeypatch.setattr(settings, "auth_login_attempts", 2)
    monkeypatch.setattr(settings, "auth_login_window_seconds", 3600)
    client = _client()
    _register(client, email="throttled@example.edu")
    for _ in range(2):
        assert (
            client.post(
                "/api/auth/login",
                json={"email": "throttled@example.edu", "password": "wrong-password-1"},
            ).status_code
            == 401
        )
    locked = client.post(
        "/api/auth/login",
        json={"email": "throttled@example.edu", "password": "wrong-password-1"},
    )
    assert locked.status_code == 429


def _auth_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def test_change_password_round_trip():
    client = _client()
    created = _register(client, email="pw@example.edu")
    headers = _auth_headers(created["tokens"]["access_token"])

    wrong = client.post(
        "/api/auth/change-password",
        json={"current_password": "wrong-password-1", "new_password": "new-correct-horse-99"},
        headers=headers,
    )
    assert wrong.status_code == 401

    short = client.post(
        "/api/auth/change-password",
        json={"current_password": "correct-horse-99", "new_password": "short"},
        headers=headers,
    )
    assert short.status_code == 422

    # Missing body is a malformed request, rejected before auth runs.
    assert (
        client.post("/api/auth/change-password", headers=headers).status_code == 422
    )

    changed = client.post(
        "/api/auth/change-password",
        json={"current_password": "correct-horse-99", "new_password": "new-correct-horse-99"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text

    old_login = client.post(
        "/api/auth/login",
        json={"email": "pw@example.edu", "password": "correct-horse-99"},
    )
    assert old_login.status_code == 401
    new_login = client.post(
        "/api/auth/login",
        json={"email": "pw@example.edu", "password": "new-correct-horse-99"},
    )
    assert new_login.status_code == 200, new_login.text


def test_delete_account_removes_credentials_and_sessions():
    client = _client()
    created = _register(client, email="gone@example.edu")
    access = created["tokens"]["access_token"]
    refresh = created["tokens"]["refresh_token"]
    headers = _auth_headers(access)

    wrong = client.request(
        "DELETE", "/api/auth/account", json={"password": "wrong-password-1"}, headers=headers
    )
    assert wrong.status_code == 401
    assert client.get("/api/auth/me", headers=headers).status_code == 200

    deleted = client.request(
        "DELETE", "/api/auth/account", json={"password": "correct-horse-99"}, headers=headers
    )
    assert deleted.status_code == 200, deleted.text

    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert (
        client.post("/api/auth/refresh", json={"refresh_token": refresh}).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "gone@example.edu", "password": "correct-horse-99"},
        ).status_code
        == 401
    )
