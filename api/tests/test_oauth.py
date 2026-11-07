import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from api.auth import oauth
from api.core.config import settings
from api.main import app

pytestmark = pytest.mark.real_auth


@pytest.fixture
def google(monkeypatch):
    monkeypatch.setattr(settings, "oauth_google_client_id", "cid")
    monkeypatch.setattr(settings, "oauth_google_client_secret", "secret")
    profile = {"value": None}

    async def fake_exchange(p, code, verifier):
        assert code == "good-code" and verifier
        return profile["value"]

    monkeypatch.setattr(oauth, "exchange", fake_exchange)
    return profile


def _sign_in(client, profile_box, profile, next_path="/runs"):
    profile_box["value"] = profile
    start = client.post("/api/auth/oauth/google/start", json={"next": next_path}).json()
    q = parse_qs(urlparse(start["authorize_url"]).query)
    assert q["code_challenge_method"] == ["S256"] and q["state"] == [start["state"]]
    return client.post(
        "/api/auth/oauth/google/callback",
        json={"code": "good-code", "state": start["state"]},
    )


def test_providers_list_only_configured(monkeypatch):
    with TestClient(app) as client:
        monkeypatch.setattr(settings, "oauth_google_client_id", "")
        assert client.get("/api/auth/oauth/providers").json() == []
        assert client.post("/api/auth/oauth/google/start", json={}).status_code == 404
        monkeypatch.setattr(settings, "oauth_google_client_id", "cid")
        monkeypatch.setattr(settings, "oauth_google_client_secret", "s")
        assert client.get("/api/auth/oauth/providers").json() == [
            {"id": "google", "label": "Google"}
        ]


def test_new_then_returning_google_user_gets_a_normal_session(google):
    sub, email = uuid.uuid4().hex, f"g-{uuid.uuid4().hex[:8]}@gmail.com"
    profile = oauth.Profile(
        subject=sub, email=email, email_verified=True, name="Kofi Boateng"
    )
    with TestClient(app) as client:
        first = _sign_in(client, google, profile)
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["next"] == "/runs"
        assert body["user"]["email"] == email and body["user"]["email_verified"] is True
        assert (
            body["user"]["has_password"] is False
            and body["user"]["display_name"] == "Kofi Boateng"
        )
        me = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {body['tokens']['access_token']}"},
        )
        assert me.status_code == 200
        again = _sign_in(client, google, profile).json()
        assert again["user"]["id"] == body["user"]["id"]
        headers = {"Authorization": f"Bearer {again['tokens']['access_token']}"}
        assert (
            client.request(
                "DELETE",
                "/api/auth/account",
                headers=headers,
                json={"password": "nope"},
            ).status_code
            == 401
        )
        assert (
            client.request(
                "DELETE", "/api/auth/account", headers=headers, json={"password": email}
            ).status_code
            == 200
        )


def test_email_collision_requires_password_then_links(google):
    email = f"c-{uuid.uuid4().hex[:8]}@example.com"
    with TestClient(app) as client:
        reg = client.post(
            "/api/auth/register", json={"accept_terms": True, "email": email, "password": "long-enough-1"}
        ).json()
        r = _sign_in(
            client,
            google,
            oauth.Profile(subject=uuid.uuid4().hex, email=email, email_verified=True),
        )
        body = r.json()
        assert "tokens" not in body and body["link_required"]["email"] == email
        token = body["link_required"]["link_token"]
        assert (
            client.post(
                "/api/auth/oauth/link", json={"link_token": token, "password": "wrong"}
            ).status_code
            == 401
        )
        linked = client.post(
            "/api/auth/oauth/link",
            json={"link_token": token, "password": "long-enough-1"},
        ).json()
        assert linked["user"]["id"] == reg["user"]["id"]
        subject = oauth.auth_security.read_signed("oauth_link", token)["s"]
        direct = _sign_in(
            client,
            google,
            oauth.Profile(subject=subject, email=email, email_verified=True),
        ).json()
        assert direct["user"]["id"] == reg["user"]["id"]


def test_bad_state_unverified_email_and_typed_tokens_are_rejected(google):
    with TestClient(app) as client:
        bad = client.post(
            "/api/auth/oauth/google/callback",
            json={"code": "good-code", "state": "forged"},
        )
        assert bad.status_code == 400
        r = _sign_in(
            client,
            google,
            oauth.Profile(subject="x", email="u@example.com", email_verified=False),
        )
        assert r.status_code == 400
        state = client.post("/api/auth/oauth/google/start", json={}).json()["state"]
        # A state token must never work as a session token.
        assert (
            client.get(
                "/api/auth/me", headers={"Authorization": f"Bearer {state}"}
            ).status_code
            == 401
        )
        # Open redirects are neutralised.
        evil = client.post(
            "/api/auth/oauth/google/start", json={"next": "//evil.example"}
        ).json()["state"]
        assert oauth.auth_security.read_signed("oauth_state", evil)["n"] == "/"
