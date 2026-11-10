import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from api.auth import email_flows, security
from api.auth.models import RefreshToken, User
from api.core.db import SessionLocal
from api.core.time import utcnow_naive
from api.extension_auth.models import ExtensionSession
from api.main import app
from tests.test_applicant_kit import kit as kit_fixture
from tests.test_applicant_kit import rows, run, upload

pytestmark = pytest.mark.real_auth
kit = kit_fixture


def connect(client, name="Chrome on Linux"):
    response = client.post("/api/app/extension/connect", json={"name": name})
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "private, no-store"
    return response.json()


def extension(pair):
    return TestClient(app, headers={"Authorization": f"Bearer {pair['access_token']}"})


def test_connect_me_sessions_and_90_day_hashed_refresh(kit):
    client, _, ids, _ = kit
    pair = connect(client, " Chrome on Linux ")
    claims = security.parse_access_claims(pair["access_token"], "ext")
    assert claims["sub"] == ids[0] and claims["sid"] == pair["session"]["id"]
    assert claims["exp"] - claims["iat"] == 15 * 60
    assert pair["session"]["name"] == "Chrome on Linux"
    assert pair["session"]["last_used_at"] is None
    grant = rows(RefreshToken, ids[0])[0]
    assert grant.audience == "ext" and grant.extension_session_id == claims["sid"]
    assert grant.token_hash == security.hash_token(pair["refresh_token"])
    assert abs((grant.expires_at - utcnow_naive()).total_seconds() - 90 * 86400) < 10
    project = client.post("/api/app/projects", json={"name": "Siwa"}).json()
    response = extension(pair).get("/api/app/extension/me")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["user"]["id"] == ids[0]
    assert data["projects"] == [{"id": project["id"], "name": "Siwa", "tagline": ""}]
    assert data["drafting"] == {"enabled": True, "remaining_today": 60}
    sessions = client.get("/api/app/extension/sessions").json()
    assert sessions[0]["id"] == claims["sid"] and sessions[0]["last_used_at"]
    assert "revoked_at" not in sessions[0]
    assert client.get("/api/app/extension/me").status_code == 401


def mounted_routes(routes):
    for route in routes:
        if hasattr(route, "effective_route_contexts"):
            yield from route.effective_route_contexts()
        else:
            yield route


def test_every_mounted_app_route_has_the_expected_ext_audience_boundary(kit):
    client = kit[0]
    pair = connect(client)
    ext = extension(pair)
    project = client.post("/api/app/projects", json={"name": "Siwa"}).json()
    doc = upload(client).json()
    application = client.post("/api/app/applications", json={"title": "Test"}).json()
    allowed = {
        ("GET", "/api/app/profile"),
        ("GET", "/api/app/projects"),
        ("GET", "/api/app/projects/{project_id}"),
        ("GET", "/api/app/documents"),
        ("GET", "/api/app/documents/usage"),
        ("GET", "/api/app/documents/{document_id}/download"),
        ("GET", "/api/app/applications"),
        ("GET", "/api/app/applications/{application_id}"),
        ("PATCH", "/api/app/applications/{application_id}"),
        ("POST", "/api/app/autofill/fill"),
        ("POST", "/api/app/autofill/feedback"),
        ("POST", "/api/app/autofill/reports"),
        ("GET", "/api/app/extension/me"),
        ("POST", "/api/app/extension/logout"),
    }
    checked = set()
    for route in mounted_routes(app.routes):
        path = getattr(route, "path", "")
        if not path.startswith("/api/app/"):
            continue
        for method in route.methods:
            checked.add((method, path))
            url = path
            for param, value in {
                "project_id": project["id"],
                "document_id": doc["id"],
                "application_id": application["id"],
            }.items():
                url = url.replace("{" + param + "}", value)
            while "{" in url:
                start, end = url.index("{"), url.index("}")
                url = url[:start] + "missing" + url[end + 1 :]
            if path.endswith("/extension/logout"):
                continue
            body = {"status": "submitted"} if method == "PATCH" else {}
            if path.endswith("/autofill/fill"):
                body = {
                    "page": {"url": "https://example.com"},
                    "fields": [],
                    "allow_drafting": False,
                }
            if path.endswith("/autofill/feedback"):
                body = {
                    "page": {"url": "https://example.com"},
                    "field": {"key": "name", "label": "Name"},
                    "filled": {
                        "value": "Name",
                        "source": "profile",
                        "rule": "matched:full_name",
                    },
                    "corrected": {"wrong_field": True},
                }
            if path.endswith("/autofill/reports"):
                body = {
                    "page": {"url": "https://example.com"},
                    "fields": [],
                    "note": "Test",
                }
            response = ext.request(method, url, json=body)
            expected = 200 if (method, path) in allowed else 401
            if (method, path) in allowed and path.endswith(
                ("/autofill/feedback", "/autofill/reports")
            ):
                expected = 204
            assert response.status_code == expected, (method, path, response.text)
    assert allowed <= checked
    assert len(checked) > len(allowed)
    assert (
        ext.post(
            "/api/app/extension/logout", json={"refresh_token": pair["refresh_token"]}
        ).status_code
        == 204
    )
    assert ext.get("/api/app/profile").status_code == 401
    for prefix in ("/api", "/api/admin"):
        assert ext.get(prefix + "/auth/me").status_code == 401


def test_refresh_rotation_and_reuse_revokes_only_that_browser(kit):
    client = kit[0]
    first, other = connect(client), connect(client, "Edge")
    response = client.post(
        "/api/app/extension/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert response.status_code == 200, response.text
    rotated = response.json()
    assert rotated["refresh_token"] != first["refresh_token"]
    assert extension(rotated).get("/api/app/profile").status_code == 200
    assert (
        client.post(
            "/api/app/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/app/extension/refresh", json={"refresh_token": first["refresh_token"]}
        ).status_code
        == 401
    )
    for pair in (first, rotated):
        assert extension(pair).get("/api/app/profile").status_code == 401
        assert (
            client.post(
                "/api/app/extension/refresh",
                json={"refresh_token": pair["refresh_token"]},
            ).status_code
            == 401
        )
    assert extension(other).get("/api/app/profile").status_code == 200
    assert len(client.get("/api/app/extension/sessions").json()) == 1


def test_concurrent_refresh_reuse_revokes_the_rotated_pair(kit):
    client = kit[0]
    pair = connect(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: client.post(
                    "/api/app/extension/refresh",
                    json={"refresh_token": pair["refresh_token"]},
                ),
                range(2),
            )
        )
    assert sorted(response.status_code for response in responses) == [200, 401]
    rotated = next(
        response.json() for response in responses if response.status_code == 200
    )
    assert extension(rotated).get("/api/app/profile").status_code == 401


def test_revoke_checks_ownership_and_kills_access_and_refresh(kit):
    client, other, ids, _ = kit
    pair = connect(client)
    sid = pair["session"]["id"]
    assert other.delete(f"/api/app/extension/sessions/{sid}").status_code == 404
    assert client.delete(f"/api/app/extension/sessions/{sid}").status_code == 204
    assert client.delete(f"/api/app/extension/sessions/{sid}").status_code == 204
    assert extension(pair).get("/api/app/extension/me").status_code == 401
    assert (
        client.post(
            "/api/app/extension/refresh", json={"refresh_token": pair["refresh_token"]}
        ).status_code
        == 401
    )
    assert rows(RefreshToken, ids[0]) == []
    assert rows(ExtensionSession, ids[0])[0].revoked_at is not None


def test_logout_cannot_revoke_a_different_browser(kit):
    first, other = connect(kit[0]), connect(kit[0], "Edge")
    ext = extension(first)
    assert (
        ext.post(
            "/api/app/extension/logout", json={"refresh_token": other["refresh_token"]}
        ).status_code
        == 401
    )
    assert extension(other).get("/api/app/extension/me").status_code == 200
    assert (
        ext.post(
            "/api/app/extension/logout", json={"refresh_token": first["refresh_token"]}
        ).status_code
        == 204
    )
    assert ext.get("/api/app/profile").status_code == 401


def test_invalid_expired_or_unbound_tokens_are_rejected(kit):
    client, _, ids, _ = kit
    pair = connect(client)

    async def expire():
        async with SessionLocal() as session:
            grant = await session.scalar(
                select(RefreshToken).where(
                    RefreshToken.token_hash
                    == security.hash_token(pair["refresh_token"])
                )
            )
            grant.expires_at = utcnow_naive() - timedelta(seconds=1)
            await session.commit()

    run(expire())
    for raw in (pair["refresh_token"], "garbage", security.new_refresh_token()[0]):
        assert (
            client.post(
                "/api/app/extension/refresh", json={"refresh_token": raw}
            ).status_code
            == 401
        )
    for raw in (
        "garbage",
        security.issue_access_token(ids[0], "admin"),
        security.issue_access_token(ids[0], "ext"),
        security.issue_access_token(ids[0], "ext", session_id=uuid.uuid4().hex),
        security.issue_access_token(ids[1], "ext", session_id=pair["session"]["id"]),
    ):
        assert (
            TestClient(app, headers={"Authorization": f"Bearer {raw}"})
            .get("/api/app/profile")
            .status_code
            == 401
        )


def test_disabled_account_rejected_on_access_and_refresh(kit):
    client, _, ids, _ = kit
    pair = connect(client)

    async def disable():
        async with SessionLocal() as session:
            user = await session.get(User, ids[0])
            user.disabled_at = utcnow_naive()
            await session.commit()

    run(disable())
    assert extension(pair).get("/api/app/extension/me").status_code == 403
    assert (
        client.post(
            "/api/app/extension/refresh", json={"refresh_token": pair["refresh_token"]}
        ).status_code
        == 403
    )


def test_password_reset_revokes_browser_access(kit):
    client, _, ids, _ = kit
    pair = connect(client)

    async def reset():
        async with SessionLocal() as session:
            raw = await email_flows._issue(
                session, ids[0], "reset", timedelta(minutes=10)
            )
            await email_flows.reset_password(session, raw, "a-new-secure-password")

    run(reset())
    assert extension(pair).get("/api/app/profile").status_code == 401
    assert rows(RefreshToken, ids[0]) == []


def test_extension_profile_hides_all_sensitive_values_and_writes_only_submitted_status(
    kit,
):
    client = kit[0]
    client.put(
        "/api/app/profile",
        json={
            "sensitive": {
                "national_id": "GHA-123456",
                "passport_number": "P123456",
                "passport_expiry": "2035-01-01",
            }
        },
    )
    ext = extension(connect(client))
    assert ext.get("/api/app/profile?reveal=1").json()["sensitive"] == {
        "national_id": "",
        "passport_number": "",
        "passport_expiry": None,
    }
    application = client.post("/api/app/applications", json={"title": "Test"}).json()
    for body in (
        {"notes": "changed"},
        {"status": "accepted"},
        {"status": "submitted", "notes": "changed"},
        {},
        {"status": None},
    ):
        assert (
            ext.patch(
                f"/api/app/applications/{application['id']}", json=body
            ).status_code
            == 403
        )
    assert (
        ext.patch(
            f"/api/app/applications/{application['id']}", json={"status": "submitted"}
        ).json()["status"]
        == "submitted"
    )
