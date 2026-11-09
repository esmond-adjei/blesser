import asyncio
import io
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete, func, select, text

from api.applicant_kit import models, schemas, service, storage
from api.auth.models import User
from api.auth.security import issue_access_token
from api.core.config import Settings, settings
from api.core.db import SessionLocal
from api.core.time import utcnow_naive
from api.main import app

pytestmark = pytest.mark.real_auth
PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def kit(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "secrets_key", Fernet.generate_key().decode())
    ids = [f"kit-{uuid.uuid4().hex}" for _ in range(2)]

    async def setup():
        async with SessionLocal() as session:
            session.add_all(
                User(
                    id=user_id,
                    email=f"{user_id}@example.com",
                    password_hash="!oauth",
                    email_verified_at=utcnow_naive(),
                )
                for user_id in ids
            )
            await session.commit()

    run(setup())
    clients = [
        TestClient(
            app, headers={"Authorization": f"Bearer {issue_access_token(user_id)}"}
        )
        for user_id in ids
    ]
    yield clients[0], clients[1], ids, tmp_path

    async def cleanup():
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.id.in_(ids)))
            await session.commit()

    run(cleanup())
    for client in clients:
        client.close()


def upload(client, content=PDF, **metadata):
    data = {"kind": "cv", "title": "My CV", **metadata}
    return client.post(
        "/api/app/documents",
        data=data,
        files={"file": ("cv.pdf", content, "application/pdf")},
    )


def rows(model, user_id):
    async def fetch():
        async with SessionLocal() as session:
            return list(
                await session.scalars(select(model).where(model.user_id == user_id))
            )

    return run(fetch())


def test_profile_created_once_email_default_and_full_replace(kit):
    client, other, ids, _ = kit
    first = client.get("/api/app/profile")
    assert first.status_code == 200, first.text
    assert first.headers["cache-control"] == "private, no-store"
    data = first.json()
    assert data["email"] == f"{ids[0]}@example.com"
    assert data["given_name"] == "" and data["education"] == []
    assert data["sensitive"] == {
        "national_id": "",
        "passport_number": "",
        "passport_expiry": None,
    }
    assert data["completeness"] == 8
    assert client.get("/api/app/profile").json() == data
    changed = client.put(
        "/api/app/profile", json={"given_name": "Ama", "skills": ["Python"]}
    ).json()
    assert changed["given_name"] == "Ama" and changed["email"] == ""
    cleared = client.put("/api/app/profile", json={}).json()
    assert cleared["given_name"] == "" and cleared["skills"] == []
    assert cleared["completeness"] == 0
    assert other.get("/api/app/profile").json()["email"] == f"{ids[1]}@example.com"
    assert len(rows(models.Profile, ids[0])) == 1


def test_sensitive_roundtrip_masking_and_raw_database_encryption(kit):
    client, _, ids, _ = kit
    sensitive = {
        "national_id": "GHA-123456789",
        "passport_number": "P76543210",
        "passport_expiry": "2030-12-31",
    }
    response = client.put("/api/app/profile", json={"sensitive": sensitive})
    assert response.status_code == 200, response.text
    assert response.json()["sensitive"] == {
        "national_id": "*********6789",
        "passport_number": "*****3210",
        "passport_expiry": "******2-31",
    }
    assert client.get("/api/app/profile?reveal=1").json()["sensitive"] == sensitive

    async def raw():
        async with SessionLocal() as session:
            return (
                await session.execute(
                    text(
                        "SELECT data::text, sensitive FROM applicant_profiles WHERE user_id=:id"
                    ),
                    {"id": ids[0]},
                )
            ).one()

    data, encrypted = run(raw())
    assert "national_id" not in data
    assert all(value not in encrypted for value in sensitive.values())
    assert rows(models.Profile, ids[0])[0].sensitive == sensitive
    assert (
        client.put("/api/app/profile?reveal=1", json={"sensitive": sensitive}).json()[
            "sensitive"
        ]
        == sensitive
    )


@pytest.mark.parametrize(
    "body",
    [
        {"given_name": "x" * 201},
        {"short_bio": "x" * 301},
        {"long_bio": "x" * 20001},
        {"website_url": "javascript:alert(1)"},
        {"website_url": "https://example.com:invalid"},
        {"headline": "Two\nlines"},
        {"linkedin_url": "https://user:password@example.com"},
        {"email": "invalid"},
        {"date_of_birth": "2040-01-01"},
        {"date_of_birth": "2024-02-30"},
        {"skills": ["x"] * 101},
        {"other_links": [{"url": "ftp://example.com"}]},
        {"education": [{"start": "2025-01-01", "end": "2024-01-01"}]},
        {"experience": [{"current": True, "end": "2024-01-01"}]},
        {"languages": [{"language": "Twi", "level": "expert"}]},
        {"references": [{"email": "broken"}]},
        {"awards": [{"year": 1800}]},
        {"sensitive": {"passport_expiry": "broken"}},
        {"sensitive": {"national_id": "*****1234"}},
        {"unknown": "value"},
    ],
)
def test_profile_validation(kit, body):
    assert kit[0].put("/api/app/profile", json=body).status_code == 422


def test_profile_completeness_ignores_empty_nested_rows_and_sensitive(kit):
    client = kit[0]
    data = {
        "given_name": "Ama",
        "family_name": "Mensah",
        "email": "ama@example.com",
        "phone": "+233200000000",
        "country_of_residence": "Ghana",
        "city": "Accra",
        "headline": "Researcher",
        "short_bio": "I study water.",
        "education": [{"institution": "UG"}],
        "experience": [{"organization": "Lab"}],
        "skills": ["Research"],
        "languages": [{"language": "Twi", "level": "native"}],
    }
    assert client.put("/api/app/profile", json=data).json()["completeness"] == 100
    data["education"] = [{}]
    data["experience"] = [{}]
    data["languages"] = [{}]
    data["sensitive"] = {"national_id": "123456789"}
    assert client.put("/api/app/profile", json=data).json()["completeness"] == 75


def test_project_crud_completeness_and_bidirectional_document_links(kit):
    client = kit[0]
    doc = upload(client).json()
    response = client.post(
        "/api/app/projects",
        json={
            "name": "Siwa",
            "document_ids": [doc["id"]],
            "logo_document_id": doc["id"],
        },
    )
    assert response.status_code == 201, response.text
    project = response.json()
    assert project["completeness"] == 8
    assert project["document_ids"] == [doc["id"]]
    assert client.get("/api/app/projects").json() == [project]
    assert client.get(f"/api/app/projects/{project['id']}").json() == project
    docs = client.get(
        "/api/app/documents", params={"project_id": project["id"], "kind": "cv"}
    ).json()
    assert docs[0]["project_ids"] == [project["id"]]
    changed = client.put(
        f"/api/app/projects/{project['id']}",
        json={"name": "Siwa II", "tagline": "Water", "document_ids": []},
    )
    assert changed.status_code == 200
    assert changed.json()["logo_document_id"] is None
    assert changed.json()["completeness"] == 17
    assert client.get("/api/app/documents").json()[0]["project_ids"] == []
    assert client.delete(f"/api/app/projects/{project['id']}").status_code == 204
    assert client.get(f"/api/app/projects/{project['id']}").status_code == 404
    assert client.get(f"/api/app/documents/{doc['id']}/download").content == PDF


@pytest.mark.parametrize(
    "body",
    [
        {"name": ""},
        {"name": "Siwa", "website_url": "file:///etc/passwd"},
        {"name": "Siwa", "stage": "funded"},
        {"name": "Siwa", "team_size": -1},
        {"name": "Siwa", "amount_sought": "NaN"},
        {"name": "Siwa", "revenue_last_12_months": "-1"},
        {"name": "Siwa", "currency": "cedis"},
        {"name": "Siwa", "founded_on": "2040-01-01"},
        {"name": "Siwa", "team": [{"email": "bad"}]},
    ],
)
def test_project_validation(kit, body):
    assert kit[0].post("/api/app/projects", json=body).status_code == 422


def test_upload_download_usage_and_delete(kit):
    client, _, ids, directory = kit
    assert client.get("/api/app/documents/usage").json() == {
        "used_bytes": 0,
        "limit_bytes": 250 * 1024 * 1024,
    }
    response = upload(client)
    assert response.status_code == 201, response.text
    doc = response.json()
    assert doc["size_bytes"] == len(PDF) and doc["content_type"] == "application/pdf"
    assert "storage_key" not in doc
    saved = rows(models.Document, ids[0])[0]
    assert (directory / saved.storage_key).read_bytes() == PDF
    assert client.get("/api/app/documents/usage").json()["used_bytes"] == len(PDF)
    response = client.get(f"/api/app/documents/{doc['id']}/download")
    assert response.content == PDF
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"
    assert client.delete(f"/api/app/documents/{doc['id']}").status_code == 204
    assert not (directory / saved.storage_key).exists()
    assert client.get("/api/app/documents/usage").json()["used_bytes"] == 0


def test_default_per_kind_on_upload_retag_and_patch(kit):
    client = kit[0]
    first = upload(client, is_default="true").json()
    second = upload(client, is_default="true").json()
    cover = upload(client, kind="cover_letter", is_default="true").json()
    assert {
        d["id"] for d in client.get("/api/app/documents").json() if d["is_default"]
    } == {second["id"], cover["id"]}
    assert (
        client.patch(
            f"/api/app/documents/{first['id']}", json={"is_default": True}
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/app/documents/{first['id']}",
            json={"kind": "cover_letter", "title": "Letter"},
        ).status_code
        == 200
    )
    docs = client.get("/api/app/documents").json()
    assert {d["id"] for d in docs if d["is_default"]} == {first["id"]}
    assert (
        client.patch(
            f"/api/app/documents/{first['id']}", json={"is_default": False}
        ).json()["is_default"]
        is False
    )


def test_upload_size_type_spoofing_and_failed_upload_cleanup(kit):
    client, _, ids, directory = kit
    assert upload(client, b"<html><script>alert(1)</script></html>").status_code == 415
    assert upload(client, b"MZ" + b"\x00" * 4096).status_code == 415
    assert upload(client, b"").status_code == 400
    assert upload(client, PDF + b" " * (15 * 1024 * 1024)).status_code == 413
    assert upload(client, PDF, kind="executable").status_code == 422
    assert upload(client, PDF, title="x" * 201).status_code == 422
    assert not rows(models.Document, ids[0])
    assert not [p for p in directory.rglob("*") if p.is_file()]


def test_allowlist_uses_content_instead_of_extension_and_client_mime(kit):
    client = kit[0]
    csv_file = client.post(
        "/api/app/documents",
        data={"kind": "budget", "title": "Budget"},
        files={
            "file": (
                "fake.exe",
                b"item,amount\nSupplies,10\n",
                "application/x-msdownload",
            )
        },
    )
    assert csv_file.status_code == 201, csv_file.text
    assert csv_file.json()["content_type"] == "text/csv"
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr(
            "[Content_Types].xml",
            '<Types><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        )
        zipped.writestr("word/document.xml", "<document/>")
    response = upload(client, archive.getvalue())
    assert response.status_code == 201, response.text
    assert (
        response.json()["content_type"]
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("malware.exe", "MZ")
    assert upload(client, archive.getvalue()).status_code == 415


def test_full_15mb_file_allowed_and_large_envelope_rejected(kit):
    client, _, ids, _ = kit
    response = upload(client, PDF + b" " * (15 * 1024 * 1024 - len(PDF)))
    assert response.status_code == 201, response.text
    assert response.json()["size_bytes"] == 15 * 1024 * 1024
    rejected = client.post(
        "/api/app/documents",
        content=b"x",
        headers={"Content-Length": str(17 * 1024 * 1024)},
    )
    assert rejected.status_code == 413
    assert len(rows(models.Document, ids[0])) == 1


def test_office_container_spoof_and_macro_content_rejected(kit):
    client = kit[0]
    for content_type in (
        "application/vnd.ms-word.document.macroEnabled.main+xml",
        "text/html",
    ):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr(
                "[Content_Types].xml",
                f'<Types><Override PartName="/word/document.xml" ContentType="{content_type}"/></Types>',
            )
            zipped.writestr("word/document.xml", "<document/>")
        assert upload(client, archive.getvalue()).status_code == 415


def test_quota_counts_existing_documents_and_releases_on_delete(kit):
    client, _, ids, directory = kit
    first = upload(client).json()

    async def almost_full():
        async with SessionLocal() as session:
            document = await session.get(models.Document, first["id"])
            document.size_bytes = 250 * 1024 * 1024 - len(PDF) + 1
            await session.commit()

    run(almost_full())
    assert upload(client).status_code == 413
    assert len(rows(models.Document, ids[0])) == 1
    assert len([p for p in directory.rglob("*") if p.is_file()]) == 1
    assert client.delete(f"/api/app/documents/{first['id']}").status_code == 204
    assert upload(client).status_code == 201


def test_answers_crud_search_word_count_and_literal_wildcards(kit):
    client = kit[0]
    project = client.post("/api/app/projects", json={"name": "Siwa"}).json()
    response = client.post(
        "/api/app/answers",
        json={
            "question": "Why Siwa?",
            "answer": "Clean water\nfor everyone.",
            "tags": ["water"],
            "project_id": project["id"],
            "word_count": 999,
        },
    )
    assert response.status_code == 201, response.text
    answer = response.json()
    assert answer["word_count"] == 4
    assert client.get(
        "/api/app/answers", params={"q": "WATER", "project_id": project["id"]}
    ).json() == [answer]
    assert client.get("/api/app/answers", params={"q": "%"}).json() == []
    assert client.get("/api/app/answers", params={"q": "_"}).json() == []
    changed = client.put(
        f"/api/app/answers/{answer['id']}",
        json={"question": "Why now?", "answer": "Three simple words"},
    ).json()
    assert (
        changed["word_count"] == 3
        and changed["tags"] == []
        and changed["project_id"] is None
    )
    assert client.delete(f"/api/app/answers/{answer['id']}").status_code == 204
    assert client.get("/api/app/answers").json() == []


@pytest.mark.parametrize(
    "body",
    [
        {"question": "", "answer": "x"},
        {"question": "x", "answer": ""},
        {"question": "x", "answer": "x", "tags": ["x"] * 31},
    ],
)
def test_answer_validation(kit, body):
    assert kit[0].post("/api/app/answers", json=body).status_code == 422


def test_other_member_gets_404_for_all_object_reads_writes_and_links(kit):
    owner, other, _, _ = kit
    project = owner.post("/api/app/projects", json={"name": "Private"}).json()
    doc = upload(owner, project_ids=[project["id"]]).json()
    answer = owner.post(
        "/api/app/answers",
        json={"question": "Private?", "answer": "Yes", "project_id": project["id"]},
    ).json()
    for method, path, body in [
        ("GET", f"/projects/{project['id']}", None),
        ("PUT", f"/projects/{project['id']}", {"name": "Stolen"}),
        ("DELETE", f"/projects/{project['id']}", None),
        ("GET", f"/documents/{doc['id']}/download", None),
        ("PATCH", f"/documents/{doc['id']}", {"title": "Stolen"}),
        ("DELETE", f"/documents/{doc['id']}", None),
        ("PUT", f"/answers/{answer['id']}", {"question": "Stolen?", "answer": "No"}),
        ("DELETE", f"/answers/{answer['id']}", None),
        ("GET", f"/documents?project_id={project['id']}", None),
        ("GET", f"/answers?project_id={project['id']}", None),
        ("POST", "/projects", {"name": "Stolen", "document_ids": [doc["id"]]}),
        ("POST", "/projects", {"name": "Stolen", "logo_document_id": doc["id"]}),
        (
            "POST",
            "/answers",
            {"question": "Stolen?", "answer": "No", "project_id": project["id"]},
        ),
    ]:
        response = other.request(method, f"/api/app{path}", json=body)
        assert response.status_code == 404, (path, response.text)
    assert upload(other, project_ids=[project["id"]]).status_code == 404
    own_doc = upload(other).json()
    assert (
        other.patch(
            f"/api/app/documents/{own_doc['id']}", json={"project_ids": [project["id"]]}
        ).status_code
        == 404
    )
    assert other.get("/api/app/projects").json() == []
    assert other.get("/api/app/answers").json() == []
    assert len(other.get("/api/app/documents").json()) == 1


def test_project_delete_unlinks_documents_and_answers_and_document_delete_clears_logo(
    kit,
):
    client = kit[0]
    doc = upload(client).json()
    project = client.post(
        "/api/app/projects",
        json={
            "name": "Siwa",
            "logo_document_id": doc["id"],
            "document_ids": [doc["id"]],
        },
    ).json()
    answer = client.post(
        "/api/app/answers",
        json={"question": "Why?", "answer": "Water", "project_id": project["id"]},
    ).json()
    assert client.delete(f"/api/app/documents/{doc['id']}").status_code == 204
    project = client.get(f"/api/app/projects/{project['id']}").json()
    assert project["logo_document_id"] is None and project["document_ids"] == []
    assert client.delete(f"/api/app/projects/{project['id']}").status_code == 204
    answer = client.get("/api/app/answers").json()[0]
    assert answer["project_id"] is None and answer["answer"] == "Water"


def test_account_deletion_cascades_everything_and_removes_only_owners_files(kit):
    client, other, ids, directory = kit
    assert (
        client.put(
            "/api/app/profile",
            json={"given_name": "Ama", "sensitive": {"national_id": "123456789"}},
        ).status_code
        == 200
    )
    project = client.post("/api/app/projects", json={"name": "Siwa"}).json()
    doc = upload(client, project_ids=[project["id"]]).json()
    assert (
        client.put(
            f"/api/app/projects/{project['id']}",
            json={
                "name": "Siwa",
                "logo_document_id": doc["id"],
                "document_ids": [doc["id"]],
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/app/answers",
            json={"question": "Why?", "answer": "Water", "project_id": project["id"]},
        ).status_code
        == 201
    )
    other_doc = upload(other).json()
    assert (
        client.request(
            "DELETE", "/api/app/auth/account", json={"password": "wrong"}
        ).status_code
        == 401
    )
    assert client.get(f"/api/app/documents/{doc['id']}/download").content == PDF
    response = client.request(
        "DELETE", "/api/app/auth/account", json={"password": f"{ids[0]}@example.com"}
    )
    assert response.status_code == 200, response.text
    for model in (models.Profile, models.Project, models.Document, models.Answer):
        assert not rows(model, ids[0])

    async def links():
        async with SessionLocal() as session:
            return await session.scalar(
                select(func.count())
                .select_from(models.DocumentProject)
                .where(models.DocumentProject.document_id == doc["id"])
            )

    assert run(links()) == 0
    assert len([p for p in directory.rglob("*") if p.is_file()]) == 1
    assert other.get(f"/api/app/documents/{other_doc['id']}/download").content == PDF
    assert client.get("/api/app/profile").status_code == 401


def test_admin_tokens_rejected_and_no_admin_or_legacy_kit_routes(kit):
    _, _, ids, _ = kit
    staff = TestClient(
        app, headers={"Authorization": f"Bearer {issue_access_token(ids[0], 'admin')}"}
    )
    anonymous = TestClient(app)
    for path in ("profile", "projects", "documents", "documents/usage", "answers"):
        assert staff.get(f"/api/app/{path}").status_code == 401
        assert staff.get(f"/api/admin/{path}").status_code == 404
        assert anonymous.get(f"/api/app/{path}").status_code == 401
        assert kit[0].get(f"/api/{path}").status_code == 404


@pytest.mark.rate_limits
def test_upload_rate_limit_before_parsing_body(kit, monkeypatch):
    from api.core.ratelimit import LIMITS

    monkeypatch.setitem(LIMITS, "kit_upload", [(1, 3600)])
    assert upload(kit[0]).status_code == 201
    blocked = kit[0].post("/api/app/documents", content=b"not multipart")
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    assert upload(kit[1]).status_code == 201


def test_concurrent_uploads_keep_one_default_and_enforce_quota(kit, monkeypatch):
    client, _, ids, _ = kit
    monkeypatch.setattr(storage, "MEMBER_LIMIT_BYTES", len(PDF))
    monkeypatch.setattr(service, "MEMBER_LIMIT_BYTES", len(PDF))
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(lambda _: upload(client, is_default="true"), range(2))
        )
    assert sorted(response.status_code for response in responses) == [201, 413]
    assert len(rows(models.Document, ids[0])) == 1
    assert client.get("/api/app/documents").json()[0]["is_default"] is True


def test_development_key_is_persistent_private_and_encrypts_without_configured_key(
    kit, monkeypatch
):
    client, _, _, directory = kit
    monkeypatch.setattr(settings, "secrets_key", "")
    monkeypatch.setattr(settings, "app_env", "development")
    response = client.put(
        "/api/app/profile", json={"sensitive": {"national_id": "123456789"}}
    )
    assert response.status_code == 200
    key = directory / ".dev-secrets-key"
    assert key.exists() and key.stat().st_mode & 0o777 == 0o600
    assert (
        client.get("/api/app/profile?reveal=1").json()["sensitive"]["national_id"]
        == "123456789"
    )
    assert client.get("/api/app/documents/usage").json()["used_bytes"] == 0


def test_production_requires_both_keys_and_allows_configured_startup():
    for auth, secret in (("", ""), ("auth", ""), ("", "secret")):
        with pytest.raises(ValidationError, match="required in production"):
            Settings(
                _env_file=None,
                app_env="production",
                auth_secret=auth,
                secrets_key=secret,
            )
    assert (
        Settings(
            _env_file=None,
            app_env="production",
            auth_secret="auth",
            secrets_key="secret",
        ).secrets_key
        == "secret"
    )


def test_completeness_of_complete_project():
    data = schemas.ProjectIn(
        name="Siwa",
        tagline="Clean water",
        website_url="https://example.com",
        sector="Water",
        country="Ghana",
        problem="Dirty water",
        solution="Filters",
        target_customers="Households",
        business_model="Sales",
        traction="Pilot",
        team=[{"name": "Ama"}],
        use_of_funds="Filters",
    ).model_dump()
    assert service.completeness(data, service.PROJECT_COMPLETENESS) == 100
