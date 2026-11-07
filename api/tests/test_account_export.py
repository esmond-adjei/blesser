import io
import json
import time
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient

from api.core import mailer
from api.core.config import settings
from api.core.time import utcnow_naive
from api.main import app
from tests.cv_fixtures import corpus_simple

pytestmark = pytest.mark.real_auth


@pytest.fixture(autouse=True)
def _storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "cv_storage_dir", str(tmp_path / "storage"))


def _account(client, verify=True):
    email = f"export-{uuid.uuid4().hex[:8]}@example.com"
    mailer.outbox.clear()
    reg = client.post(
        "/api/auth/register", json={"accept_terms": True, "email": email, "password": "long-enough-1"}
    ).json()
    headers = {"Authorization": f"Bearer {reg['tokens']['access_token']}"}
    if verify:
        token = mailer.outbox[-1].text.split("token=")[1].split()[0]
        assert client.post("/api/auth/verify", json={"token": token}).status_code == 200
    return email, headers


def _wait_ready(client, headers):
    for _ in range(50):
        rows = client.get("/api/account/exports", headers=headers).json()
        if rows and rows[0]["status"] != "pending":
            return rows[0]
        time.sleep(0.1)
    raise AssertionError("export never finished")


def test_unverified_accounts_cannot_export():
    with TestClient(app) as client:
        _, headers = _account(client, verify=False)
        r = client.post("/api/account/exports", headers=headers)
        assert r.status_code == 403 and "Confirm your email" in r.json()["detail"]


def test_export_is_complete_secret_free_and_link_scoped():
    with TestClient(app) as client:
        _, headers = _account(client)
        client.post(
            "/api/applications",
            headers=headers,
            json={"school": "ETH", "program": "PhD"},
        )
        client.patch(
            "/api/providers/anthropic",
            headers=headers,
            json={"model": "claude-x", "api_key": "test-key-not-a-secret"},
        )
        doc = client.post(
            "/api/cv/documents",
            headers=headers,
            files={"file": ("cv.docx", corpus_simple(), "application/octet-stream")},
            data={"title": "CV"},
        ).json()
        created = client.post("/api/account/exports", headers=headers)
        assert created.status_code == 200, created.text
        assert client.post("/api/account/exports", headers=headers).status_code in (
            200,
            409,
        )
        row = _wait_ready(client, headers)
        assert row["status"] == "ready", row

        link = client.post(
            f"/api/account/exports/{row['id']}/link", headers=headers
        ).json()["url"]
        resp = client.get(link)
        assert (
            resp.status_code == 200
            and resp.headers["content-type"] == "application/zip"
        )
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = set(zf.namelist())
        assert {
            "manifest.json",
            "account.json",
            "README.txt",
            "data/applications.json",
        } <= names
        assert any(n.startswith(f"files/cv/{doc['id']}/") for n in names)
        assert json.loads(zf.read("data/applications.json"))[0]["school"] == "ETH"
        blob = b"".join(zf.read(n) for n in names)
        for secret in (b"test-key-not-a-secret", b"password_hash", b"token_hash"):
            assert secret not in blob
        assert (
            "auth_refresh_tokens" not in json.loads(zf.read("manifest.json"))["tables"]
        )

        _, other = _account(client)
        assert (
            client.post(
                f"/api/account/exports/{row['id']}/link", headers=other
            ).status_code
            == 404
        )
        assert (
            client.get(f"/api/account/exports/{row['id']}/file?t=forged").status_code
            == 404
        )
        # A Bearer session token is not a download token either.
        bearer = headers["Authorization"].split()[1]
        assert (
            client.get(f"/api/account/exports/{row['id']}/file?t={bearer}").status_code
            == 404
        )


def test_account_deletion_removes_export_archives():
    from api.account.export import exports_root

    with TestClient(app) as client:
        _, headers = _account(client)
        me = client.get("/api/auth/me", headers=headers).json()
        assert client.post("/api/account/exports", headers=headers).status_code == 200
        assert _wait_ready(client, headers)["status"] == "ready"
        user_dir = exports_root() / me["id"]
        assert any(user_dir.iterdir())
        resp = client.request(
            "DELETE",
            "/api/auth/account",
            json={"password": "long-enough-1"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
    assert not user_dir.exists()


def test_global_sweep_drops_expired_and_orphaned_archives():
    import asyncio
    from datetime import timedelta

    from sqlalchemy import update

    from api.account import export as account_export
    from api.account.models import AccountExport
    from api.core.db import SessionLocal

    with TestClient(app) as client:
        _, headers = _account(client)
        assert client.post("/api/account/exports", headers=headers).status_code == 200
        row = _wait_ready(client, headers)
        me = client.get("/api/auth/me", headers=headers).json()
    path = account_export.archive_path(me["id"], row["id"])
    assert path.exists()
    orphan = account_export.exports_root() / "deleted-account-id"
    orphan.mkdir(parents=True)
    (orphan / "old.zip").write_bytes(b"zip")

    async def expire_and_sweep():
        async with SessionLocal() as session:
            await session.execute(
                update(AccountExport)
                .where(AccountExport.id == row["id"])
                .values(expires_at=utcnow_naive() - timedelta(minutes=1))
            )
            await session.commit()
            # No request from the owner: the worker's global pass alone.
            return await account_export.sweep_expired_exports(session)

    assert asyncio.run(expire_and_sweep()) >= 1
    assert not path.exists()
    assert not orphan.exists()
