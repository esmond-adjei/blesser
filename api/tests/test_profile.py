from fastapi.testclient import TestClient

from api.main import app


def test_display_name_normalizes_and_clears(monkeypatch):
    # Real Bearer auth (not the conftest stub) so /auth/me reads the row.
    import uuid

    from api.auth.routes import get_current_user

    saved = app.dependency_overrides.pop(get_current_user, None)
    try:
        with TestClient(app) as client:
            email = f"profile-{uuid.uuid4().hex[:8]}@example.com"
            reg = client.post(
                "/api/auth/register",
                json={"accept_terms": True, "email": email, "password": "long-enough-pw-1"},
            )
            headers = {
                "Authorization": f"Bearer {reg.json()['tokens']['access_token']}"
            }
            r = client.patch(
                "/api/auth/me",
                json={"display_name": "  Ada \t Lovelace\u0007 "},
                headers=headers,
            )
            assert r.status_code == 200, r.text
            assert r.json()["display_name"] == "Ada Lovelace"
            assert (
                client.get("/api/auth/me", headers=headers).json()["display_name"]
                == "Ada Lovelace"
            )
            too_long = client.patch(
                "/api/auth/me", json={"display_name": "x" * 81}, headers=headers
            )
            assert too_long.status_code == 400
            cleared = client.patch(
                "/api/auth/me", json={"display_name": "   "}, headers=headers
            )
            assert cleared.json()["display_name"] is None
    finally:
        if saved is not None:
            app.dependency_overrides[get_current_user] = saved
