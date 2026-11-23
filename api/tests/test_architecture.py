import asyncio
from datetime import timedelta
from functools import lru_cache

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from api.admin import audit as audit_module
from api.applications.models import Application
from api.auth import security
from api.auth.models import RefreshToken, User
from api.core.config import settings
from api.core.db import SessionLocal
from api.core.time import utcnow_naive
from api.editorial import models as m
from api.editorial.service import defaults
from api.main import app
from api.opportunities import service as opportunities
from api.opportunities.archive import auto_archive
from api.opportunities.models import Opportunity
from api.opportunities.schemas import AgentOpportunityIn
from api.scans.models import ScanTask
from api.todos.models import Todo

pytestmark = pytest.mark.real_auth
PASSWORD = "correct-horse-architecture"


def run(coro):
    return asyncio.run(coro)


@lru_cache
def password_hash():
    return security.hash_password(PASSWORD)


async def clean():
    async with SessionLocal() as session:
        for model in (
            Todo,
            Application,
            m.AuditLog,
            m.Collection,
            m.SiteContent,
            m.SiteSetting,
            Opportunity,
        ):
            await session.execute(delete(model))
        await session.execute(delete(User).where(User.id.like("arch-%")))
        session.add_all([m.SiteSetting(key=k, value=v) for k, v in defaults().items()])
        await session.commit()


@pytest.fixture(autouse=True)
def isolated():
    run(clean())
    security._attempts.clear()
    yield
    run(clean())


def user(role="member", *, name=None, verified=True, disabled=False):
    id = f"arch-{name or role}"

    async def create():
        async with SessionLocal() as session:
            row = User(
                id=id,
                email=f"{id}@example.com",
                role=role,
                password_hash=password_hash(),
                email_verified_at=utcnow_naive() if verified else None,
                disabled_at=utcnow_naive() if disabled else None,
            )
            session.add(row)
            await session.commit()

    run(create())
    return id


def headers(id, audience="admin"):
    return {"Authorization": f"Bearer {security.issue_access_token(id, audience)}"}


def client(id=None, audience="admin", **kwargs):
    return TestClient(app, headers=headers(id, audience) if id else {}, **kwargs)


def add(title="Climate Grant", **values):
    async def create():
        async with SessionLocal() as session:
            row = Opportunity(
                title=title,
                category="startup",
                slug=title.lower().replace(" ", "-"),
                dedupe_key=opportunities.dedupe_key("", title),
                **values,
            )
            session.add(row)
            await session.commit()
            return {"id": row.id, "slug": row.slug}

    return run(create())


def read(model, id):
    async def fetch():
        async with SessionLocal() as session:
            return await session.get(model, id)

    return run(fetch())


def set_setting(key, value):
    async def update():
        async with SessionLocal() as session:
            row = await session.get(m.SiteSetting, key)
            row.value = value
            await session.commit()

    run(update())


def create_staff_opportunity(c, **values):
    response = c.post(
        "/api/admin/opportunities",
        json={"title": "Staff Grant", "category": "startup", **values},
    )
    assert response.status_code == 200, response.text
    return response.json()


PUBLIC_FIELDS = {
    "id",
    "slug",
    "title",
    "organization",
    "category",
    "kind",
    "summary",
    "eligibility",
    "benefits",
    "location",
    "countries",
    "requirements",
    "tags",
    "deadline",
    "deadline_date",
    "rolling",
    "link",
    "source_url",
    "verified_at",
    "published_at",
    "is_open",
    "days_left",
    "closed",
}
MEMBER_FIELDS = PUBLIC_FIELDS | {"audience", "found_by", "created_at", "is_new", "match_score", "match_terms", "in_review"}


@pytest.mark.parametrize(
    "status", ["draft", "in_review", "published", "archived", "hidden"]
)
@pytest.mark.parametrize("audience", ["public", "members"])
def test_visibility_and_exact_public_schema(status, audience):
    row = add(
        status=status,
        audience=audience,
        editor_note="private staff note",
        review_reason="reported",
    )
    c = client()
    response = c.get(f"/api/public/opportunities/{row['slug']}")
    visible = audience == "public" and status in ("published", "archived")
    assert response.status_code == (200 if visible else 404)
    if visible:
        assert set(response.json()) == PUBLIC_FIELDS
        assert response.json()["closed"] == (status == "archived")
        assert response.json()["is_open"] == (status != "archived")
    list_response = c.get("/api/public/opportunities")
    assert list_response.json()["total"] == int(
        audience == "public" and status == "published"
    )
    assert (
        list_response.headers["cache-control"]
        == "public, max-age=60, s-maxage=300, stale-while-revalidate=3600"
    )
    assert c.get(
        f"/api/public/opportunities/{row['slug']}/calendar.ics"
    ).status_code == (200 if visible else 404)


@pytest.mark.parametrize(
    "path",
    [
        "/api/app/opportunities",
        "/api/app/opportunities/facets",
        "/api/app/applications",
        "/api/app/todos",
        "/api/app/scans",
        "/api/app/notifications",
        "/api/app/calendar/feed",
        "/api/app/auth/me",
        "/api/opportunities",
        "/api/applications",
    ],
)
def test_member_routes_reject_admin_tokens(path):
    id = user("admin")
    assert client(id).get(path).status_code == 401


@pytest.mark.parametrize("role", ["member", "editor", "admin"])
def test_audience_role_and_refresh_matrix(role):
    id = user(role)
    c = client()
    member = c.post(
        "/api/app/auth/login", json={"email": f"{id}@example.com", "password": PASSWORD}
    )
    assert member.status_code == 200
    pair = member.json()["tokens"]
    claims = jwt.decode(pair["access_token"], options={"verify_signature": False})
    assert claims["aud"] == "app"
    assert (
        c.get(
            "/api/admin/auth/me",
            headers={"Authorization": f"Bearer {pair['access_token']}"},
        ).status_code
        == 401
    )
    assert (
        c.post(
            "/api/admin/auth/refresh", json={"refresh_token": pair["refresh_token"]}
        ).status_code
        == 401
    )
    login = c.post(
        "/api/admin/auth/login",
        json={"email": f"{id}@example.com", "password": PASSWORD},
    )
    if role == "member":
        assert login.status_code == 403
        return
    assert login.status_code == 200, login.text
    staff = login.json()
    assert staff["user"]["role"] == role
    assert (
        jwt.decode(staff["access_token"], options={"verify_signature": False})["aud"]
        == "admin"
    )
    raw = staff["refresh_token"]

    async def expiry():
        async with SessionLocal() as session:
            grant = (
                await session.execute(
                    select(RefreshToken).where(
                        RefreshToken.token_hash == security.hash_token(raw)
                    )
                )
            ).scalar_one()
            return (grant.expires_at - utcnow_naive()).total_seconds()

    assert 43100 < run(expiry()) <= 43200
    assert (
        c.post("/api/app/auth/refresh", json={"refresh_token": raw}).status_code == 401
    )
    assert (
        c.post("/api/app/auth/logout", json={"refresh_token": raw}).status_code == 200
    )
    fresh = c.post("/api/admin/auth/refresh", json={"refresh_token": raw})
    assert fresh.status_code == 200, fresh.text
    assert (
        c.post("/api/admin/auth/refresh", json={"refresh_token": raw}).status_code
        == 401
    )
    token = fresh.json()["tokens"]["refresh_token"]
    assert (
        c.post("/api/admin/auth/logout", json={"refresh_token": token}).status_code
        == 200
    )
    assert (
        c.post("/api/admin/auth/refresh", json={"refresh_token": token}).status_code
        == 401
    )
    assert (
        c.post("/api/admin/auth/logout", json={"refresh_token": token}).status_code
        == 200
    )
    assert client(id).get("/api/admin/auth/me").status_code == 200


@pytest.mark.parametrize(
    "path,method",
    [
        ("/settings", "get"),
        ("/settings", "put"),
        ("/users", "get"),
        ("/users/nope", "patch"),
        ("/audit", "get"),
    ],
)
def test_editors_cannot_access_admin_only_routes(path, method):
    id = user("editor")
    assert getattr(client(id), method)(f"/api/admin{path}").status_code == 403


@pytest.mark.parametrize("verified,disabled", [(False, False), (True, True)])
def test_staff_login_requires_verified_enabled_account(verified, disabled):
    id = user("admin", verified=verified, disabled=disabled)
    c = client()
    assert (
        c.post(
            "/api/admin/auth/login",
            json={"email": f"{id}@example.com", "password": PASSWORD},
        ).status_code
        == 403
    )
    assert client(id).get("/api/admin/auth/me").status_code == 403


def test_disabled_user_tokens_and_refresh_stop_working():
    id = user()
    c = client()
    pair = c.post(
        "/api/app/auth/login", json={"email": f"{id}@example.com", "password": PASSWORD}
    ).json()["tokens"]

    async def disable():
        async with SessionLocal() as session:
            row = await session.get(User, id)
            row.disabled_at = utcnow_naive()
            await session.commit()

    run(disable())
    assert client(id, "app").get("/api/app/auth/me").status_code == 403
    assert (
        c.post(
            "/api/app/auth/refresh", json={"refresh_token": pair["refresh_token"]}
        ).status_code
        == 403
    )
    assert (
        c.post(
            "/api/app/auth/login",
            json={"email": f"{id}@example.com", "password": PASSWORD},
        ).status_code
        == 403
    )


def test_member_catalogue_new_filters_and_aliases():
    id = user()
    add(audience="members")
    add(
        "Old Public Grant",
        audience="public",
        created_at=utcnow_naive() - timedelta(days=9),
    )
    add("Review Grant", status="in_review")
    c = client(id, "app")
    body = c.get("/api/app/opportunities").json()
    assert body["total"] == 2
    assert set(body["items"][0]) == MEMBER_FIELDS
    assert c.get("/api/opportunities").json() == body
    assert c.get("/api/app/opportunities", params={"new": True}).json()["total"] == 1
    assert (
        c.get("/api/app/opportunities", params={"audience": "members"}).json()["total"]
        == 1
    )
    assert c.get("/api/app/opportunities/facets").json()["total"] == 2
    assert c.get("/api/app/opportunities/climate-grant").status_code == 200
    assert c.get("/api/public/opportunities").json()["total"] == 1
    assert c.get("/api/public/facets").json()["total"] == 1


def test_staff_crud_counts_history_and_audits():
    c = client(user("editor"))
    row = create_staff_opportunity(c, editor_note="private", review_reason="agent_find")
    assert row["status"] == "draft" and row["source"] == "staff"
    response = c.patch(
        f"/api/admin/opportunities/{row['id']}",
        json={
            "status": "published",
            "audience": "public",
            "featured_rank": 2,
            "deadline": "2027-12-01",
        },
    )
    assert response.status_code == 200, response.text
    published = response.json()
    assert published["published_by"] == "arch-editor"
    assert published["published_at"].endswith("Z")
    assert published["deadline_date"] == "2027-12-01"
    assert published["review_reason"] is None
    detail = c.get(f"/api/admin/opportunities/{row['id']}").json()
    assert [h["action"] for h in detail["history"]] == [
        "opportunity.update",
        "opportunity.create",
    ]
    assert detail["history"][0]["before"]["status"] == "draft"
    assert detail["history"][0]["after"]["status"] == "published"
    assert detail["trace_excerpt"] is None
    assert c.get("/api/admin/opportunities/counts").json()["published_public"] == 1
    for params in (
        {"q": "Staff", "status": "published"},
        {"source": "staff", "audience": "public", "sort": "deadline"},
        {"sort": "created"},
        {"category": "startup", "kind": "other"},
    ):
        assert c.get("/api/admin/opportunities", params=params).json()["total"] == 1
    assert (
        c.get("/api/admin/opportunities", params={"review_reason": "reported"}).json()[
            "total"
        ]
        == 0
    )
    assert c.delete(f"/api/admin/opportunities/{row['id']}").status_code == 200
    assert c.get(f"/api/admin/opportunities/{row['id']}").status_code == 404


def test_slug_history_redirect_visibility_and_collision():
    c = client(user("editor"))
    row = create_staff_opportunity(
        c, status="published", audience="public", slug="first-grant"
    )
    assert (
        c.patch(
            f"/api/admin/opportunities/{row['id']}", json={"slug": "second-grant"}
        ).status_code
        == 200
    )
    assert (
        c.patch(
            f"/api/admin/opportunities/{row['id']}", json={"slug": "third-grant"}
        ).status_code
        == 200
    )
    public = client()
    for old in ("first-grant", "second-grant"):
        for suffix in ("", "/calendar.ics"):
            response = public.get(
                f"/api/public/opportunities/{old}{suffix}", follow_redirects=False
            )
            assert response.status_code == 301
            assert (
                response.headers["location"]
                == f"/api/public/opportunities/third-grant{suffix}"
            )
    assert (
        c.post(
            "/api/admin/opportunities",
            json={
                "title": "Another Grant",
                "category": "startup",
                "slug": "first-grant",
            },
        ).status_code
        == 409
    )
    assert (
        c.patch(
            f"/api/admin/opportunities/{row['id']}", json={"audience": "members"}
        ).status_code
        == 200
    )
    assert public.get("/api/public/opportunities/first-grant").status_code == 404
    assert (
        c.patch(
            f"/api/admin/opportunities/{row['id']}",
            json={"audience": "public", "status": "hidden"},
        ).status_code
        == 200
    )
    assert public.get("/api/public/opportunities/first-grant").status_code == 404


@pytest.mark.parametrize(
    "action,status,audience",
    [
        ("publish_public", "published", "public"),
        ("publish_members", "published", "members"),
        ("archive", "archived", "public"),
        ("hide", "hidden", "public"),
        ("to_review", "in_review", "public"),
    ],
)
def test_bulk_actions_are_audited(action, status, audience):
    c = client(user("editor"))
    row = add(status="draft")
    response = c.post(
        "/api/admin/opportunities/bulk",
        json={"ids": [row["id"], row["id"]], "action": action},
    )
    assert response.json() == {"updated": 1}
    stored = read(Opportunity, row["id"])
    assert (stored.status, stored.audience) == (status, audience)
    detail = c.get(f"/api/admin/opportunities/{row['id']}").json()
    assert detail["history"][0]["action"] == f"opportunity.bulk.{action}"


def test_audit_and_bulk_failure_roll_back_all_changes(monkeypatch):
    id = user("editor")
    c = client(id, raise_server_exceptions=False)
    row = add(status="draft")
    assert (
        c.post(
            "/api/admin/opportunities/bulk",
            json={"ids": [row["id"], "missing"], "action": "hide"},
        ).status_code
        == 404
    )
    assert read(Opportunity, row["id"]).status == "draft"

    async def fail(*args, **kwargs):
        raise RuntimeError("audit write failed")

    monkeypatch.setattr(audit_module, "audited", fail)
    import api.admin.service as admin_service

    monkeypatch.setattr(admin_service, "audited", fail)
    assert (
        c.patch(
            f"/api/admin/opportunities/{row['id']}", json={"status": "published"}
        ).status_code
        == 500
    )
    assert read(Opportunity, row["id"]).status == "draft"


def test_merge_repoints_tracking_and_reverify_queues_one_task():
    staff = client(user("editor"))
    member = client(user(), "app")
    source, target = add(), add("Target Grant")
    application = member.post(f"/api/app/opportunities/{source['id']}/track").json()
    merged = staff.post(
        f"/api/admin/opportunities/{source['id']}/merge", json={"into_id": target["id"]}
    )
    assert merged.status_code == 200 and merged.json()["id"] == target["id"]
    assert read(Opportunity, source["id"]).status == "hidden"
    assert read(Application, application["id"]).opportunity_id == target["id"]
    assert (
        staff.post(
            f"/api/admin/opportunities/{target['id']}/merge",
            json={"into_id": target["id"]},
        ).status_code
        == 400
    )
    response = staff.post(f"/api/admin/opportunities/{target['id']}/reverify")
    assert response.status_code == 202

    async def tasks():
        async with SessionLocal() as session:
            return (
                (
                    await session.execute(
                        select(ScanTask).where(
                            ScanTask.scan_id == response.json()["scan_id"]
                        )
                    )
                )
                .scalars()
                .all()
            )

    queued = run(tasks())
    assert (
        len(queued) == 1
        and queued[0].task_type == "reverify_opportunity"
        and queued[0].target == target["id"]
    )


def test_collections_site_sitemap_and_resolved_reports():
    c = client(user("editor"))
    public = client()
    row = add(featured_rank=1, deadline_date=utcnow_naive().date() + timedelta(days=3))
    private = add("Private Grant", audience="members")
    response = c.post(
        "/api/admin/collections",
        json={
            "slug": "students",
            "title": "For students",
            "published": True,
            "item_ids": [row["id"], private["id"]],
        },
    )
    assert response.status_code == 200, response.text
    collection = response.json()
    assert len(c.get("/api/admin/collections").json()) == 1
    listed = public.get("/api/public/collections").json()[0]
    assert listed["item_ids"] == [row["id"]]
    assert set(listed["items"][0]) == PUBLIC_FIELDS
    assert (
        public.get("/api/public/collections/students").json()["items"][0]["id"]
        == row["id"]
    )
    assert public.get("/api/public/collections/missing").status_code == 404
    assert (
        c.patch(
            f"/api/admin/collections/{collection['id']}",
            json={"intro": "Selected grants", "filter": {"category": "startup"}},
        ).status_code
        == 200
    )
    assert (
        public.get("/api/public/collections/students").json()["items"][0]["id"]
        == row["id"]
    )
    assert (
        c.patch(
            f"/api/admin/collections/{collection['id']}",
            json={"filter": {"public_only": False}},
        ).status_code
        == 400
    )
    content = {
        "hero_title": "Find funding",
        "hero_subtitle": "Open calls",
        "announcement": {
            "text": "New round",
            "link": "/opportunities",
            "starts_on": "2000-01-01",
            "ends_on": "2000-01-02",
        },
    }
    assert c.put("/api/admin/site", json=content).status_code == 200
    assert c.get("/api/admin/site").json() == content
    site = public.get("/api/public/site").json()
    assert site["content"]["announcement"] is None
    assert [r["id"] for r in site["featured"]] == [row["id"]]
    assert [r["id"] for r in site["closing_soon"]] == [row["id"]]
    sitemap = public.get("/api/public/sitemap").json()
    assert [r["slug"] for r in sitemap["opportunities"]] == [row["slug"]]
    assert sitemap["collections"] == [{"slug": "students"}]
    assert (
        public.post(
            f"/api/public/opportunities/{row['slug']}/report",
            json={"reason": "Wrong deadline", "email": "visitor@example.com"},
        ).status_code
        == 202
    )
    reports = c.get("/api/admin/reports").json()
    assert len(reports) == 1 and reports[0]["reason"] == "Wrong deadline"
    assert read(Opportunity, row["id"]).review_reason == "reported"
    resolved = c.patch(
        f"/api/admin/reports/{reports[0]['id']}", json={"resolved": True}
    )
    assert resolved.json()["resolved"] is True
    assert c.delete(f"/api/admin/collections/{collection['id']}").status_code == 200
    assert public.get("/api/public/collections").json() == []


def test_settings_agent_defaults_submission_defaults_and_hidden_invariant():
    c = client(user("admin"))
    values = c.get("/api/admin/settings").json()
    assert values["agent_default"] == {"status": "published", "audience": "members"}
    assert values["community_default"] == {"status": "in_review"}
    values["agent_default"] = {"status": "in_review", "audience": "public"}
    values["community_default"] = {"status": "draft"}
    values["member_scan_limits"] = {"per_hour": 1, "per_day": 2}
    assert c.put("/api/admin/settings", json=values).status_code == 200
    public = client()
    response = public.post(
        "/api/public/submissions",
        json={
            "title": "Community Grant",
            "category": "startup",
            "link": "https://example.com/grant",
            "email": "visitor@example.com",
        },
    )
    assert response.status_code == 201
    submitted = read(Opportunity, response.json()["id"])
    assert submitted.status == "draft" and submitted.created_by is None

    async def save():
        async with SessionLocal() as session:
            data = AgentOpportunityIn(
                title="Agent Grant",
                category="startup",
                source_url="https://example.com/agent",
            )
            row, created, _ = await opportunities.upsert_from_agent(
                session, user_id=None, scan_id=None, data=data
            )
            assert (
                created
                and row.status == "in_review"
                and row.audience == "public"
                and row.review_reason == "agent_find"
            )
            row.status = "hidden"
            await session.commit()
            row, created, _ = await opportunities.upsert_from_agent(
                session, user_id=None, scan_id=None, data=data
            )
            assert not created and row.status == "hidden"
            await session.commit()

    run(save())


@pytest.mark.rate_limits
def test_public_submission_and_report_limits():
    c = client()
    for n in range(5):
        response = c.post(
            "/api/public/submissions",
            json={
                "title": f"Grant {n}",
                "category": "startup",
                "link": "https://example.com/grant",
            },
        )
        assert response.status_code == 201
    response = c.post(
        "/api/public/submissions",
        json={
            "title": "One more",
            "category": "startup",
            "link": "https://example.com/grant",
        },
    )
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0
    row = add()
    for _ in range(10):
        assert (
            c.post(
                f"/api/public/opportunities/{row['slug']}/report",
                json={"reason": "Check this"},
            ).status_code
            == 202
        )
    assert (
        c.post(
            f"/api/public/opportunities/{row['slug']}/report",
            json={"reason": "Check this"},
        ).status_code
        == 429
    )


def test_users_self_demotion_last_admin_and_audit_filters():
    admin = user("admin")
    member = user()
    c = client(admin)
    assert (
        c.get("/api/admin/users", params={"q": member, "role": "member"}).json()[
            "total"
        ]
        == 1
    )
    assert (
        c.patch(f"/api/admin/users/{admin}", json={"role": "member"}).status_code == 400
    )
    assert (
        c.patch(f"/api/admin/users/{admin}", json={"disabled": True}).status_code == 400
    )
    promoted = c.patch(f"/api/admin/users/{member}", json={"role": "admin"})
    assert promoted.status_code == 200 and promoted.json()["role"] == "admin"
    assert (
        c.patch(f"/api/admin/users/{member}", json={"disabled": True}).status_code
        == 200
    )
    assert (
        c.patch(f"/api/admin/users/{admin}", json={"disabled": True}).status_code == 400
    )
    assert (
        c.patch(
            f"/api/admin/users/{member}", json={"disabled": False, "role": "editor"}
        ).status_code
        == 200
    )
    audit = c.get(
        "/api/admin/audit",
        params={
            "actor_id": admin,
            "entity_type": "user",
            "entity_id": member,
            "action": "user.role",
        },
    ).json()
    assert audit["total"] == 2 and all(
        r["actor_email"] == f"{admin}@example.com" for r in audit["items"]
    )
    assert c.patch("/api/admin/audit/anything", json={}).status_code == 404
    assert c.get("/api/admin/applications").status_code == 404


def test_last_admin_cannot_be_demoted_by_another_admin():
    admin = user("admin")
    other = user("admin", name="other")
    c = client(other)
    assert (
        c.patch(f"/api/admin/users/{admin}", json={"role": "editor"}).status_code == 200
    )

    async def promote_actor():
        async with SessionLocal() as session:
            actor = await session.get(User, other)
            target = await session.get(User, admin)
            actor.role, target.role = "admin", "admin"
            target.disabled_at = utcnow_naive()
            await session.commit()

    run(promote_actor())
    assert client(admin).get("/api/admin/users").status_code == 403
    assert (
        c.patch(f"/api/admin/users/{other}", json={"disabled": True}).status_code == 400
    )


def test_admin_scans_have_owner_and_traces():
    c = client(user("editor"))
    response = c.post(
        "/api/admin/scans", json={"categories": ["student"], "region": "Ghana"}
    )
    assert response.status_code == 200, response.text
    scan = response.json()
    all_scans = c.get("/api/admin/scans", params={"limit": 1}).json()
    assert all_scans[0]["id"] == scan["id"]
    assert all_scans[0]["owner_email"] == "arch-editor@example.com"
    assert len(all_scans[0]["tasks"]) == 1


def test_registration_tracks_slug_and_default_community_review():
    row = add()
    c = client()
    response = c.post(
        "/api/app/auth/register",
        json={
            "email": "arch-register@example.com",
            "password": PASSWORD,
            "accept_terms": True,
            "track": row["slug"],
        },
    )
    assert response.status_code == 200, response.text
    token = response.json()["tokens"]["access_token"]
    member = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    tracked = member.get("/api/app/opportunities/tracked").json()
    assert row["id"] in tracked
    submission = member.post(
        "/api/app/opportunities",
        json={
            "title": "Shared Grant",
            "category": "startup",
            "link": "https://example.com/grant",
        },
    )
    assert submission.status_code == 200
    stored = read(Opportunity, submission.json()["id"])
    assert stored.status == "in_review" and stored.review_reason == "new_submission"


def test_auto_archive_runs_daily_respects_setting_and_skips_rolling():
    today = utcnow_naive().date()
    closed = add(deadline_date=today - timedelta(days=1))
    current = add("Today Grant", deadline_date=today)
    rolling = add(
        "Rolling Grant", deadline_date=today - timedelta(days=1), rolling=True
    )
    review = add(
        "Review Grant", deadline_date=today - timedelta(days=1), status="in_review"
    )

    async def archive():
        async with SessionLocal() as session:
            return await auto_archive(session)

    set_setting("auto_archive", False)
    assert run(archive()) == 0
    set_setting("auto_archive", True)
    assert run(archive()) == 1
    assert run(archive()) == 0
    assert read(Opportunity, closed["id"]).status == "archived"
    for row in (current, rolling, review):
        assert read(Opportunity, row["id"]).status != "archived"
    assert (
        client().get(f"/api/public/opportunities/{closed['slug']}").json()["closed"]
        is True
    )


def test_ops_emails_only_seed_verified_members_at_boot(monkeypatch):
    from api.auth.service import seed_admins

    member = user()
    unverified = user(name="unverified", verified=False)
    editor = user("editor")
    monkeypatch.setattr(
        settings,
        "ops_admin_emails",
        ",".join(f"{id}@example.com" for id in (member, unverified, editor)),
    )
    assert client(member).get("/api/admin/auth/me").status_code == 403

    async def seed():
        async with SessionLocal() as session:
            await seed_admins(session)

    run(seed())
    assert read(User, member).role == "admin"
    assert read(User, unverified).role == "member"
    assert read(User, editor).role == "editor"
    monkeypatch.setattr(settings, "ops_admin_emails", "")
    assert client(member).get("/api/admin/auth/me").status_code == 200


def test_admin_opportunity_timestamps_accept_offsets_and_serialize_utc():
    c = client(user("editor"))
    row = create_staff_opportunity(
        c,
        verified_at="2026-11-09T10:00:00+02:00",
        published_at="2026-11-09T12:00:00Z",
        status="published",
    )
    assert row["verified_at"] == "2026-11-09T08:00:00Z"
    assert row["published_at"] == "2026-11-09T12:00:00Z"
    patched = c.patch(
        f"/api/admin/opportunities/{row['id']}",
        json={"verified_at": "2026-11-09T11:00:00-04:00"},
    )
    assert patched.status_code == 200
    assert patched.json()["verified_at"] == "2026-11-09T15:00:00Z"


@pytest.mark.rate_limits
def test_member_quotas_change_immediately_and_deleted_scans_still_count():
    c = client(user(), "app")
    set_setting("member_scan_limits", {"per_hour": 1, "per_day": 5})
    started = c.post("/api/app/scans", json={"categories": ["startup"]})
    assert started.status_code == 200
    assert c.delete(f"/api/app/scans/{started.json()['id']}").status_code == 200
    assert c.post("/api/app/scans", json={"categories": ["startup"]}).status_code == 429
    set_setting("member_scan_limits", {"per_hour": 2, "per_day": 5})
    assert c.post("/api/app/scans", json={"categories": ["startup"]}).status_code == 200
    set_setting("member_scan_limits", {"per_hour": 0, "per_day": 0})
    assert c.post("/api/app/scans", json={"categories": ["startup"]}).status_code == 429


def test_duplicate_submission_does_not_disclose_hidden_listing():
    row = add(status="hidden", summary="Unpublished editorial content")
    c = client(user(), "app")
    response = c.post(
        "/api/app/opportunities",
        json={
            "title": "Climate Grant",
            "category": "startup",
            "link": "https://example.com/grant",
        },
    )
    assert response.status_code == 409
    assert "Unpublished editorial content" not in response.text
    assert read(Opportunity, row["id"]).status == "hidden"
    public = client().post(
        "/api/public/submissions",
        json={
            "title": "Climate Grant",
            "category": "startup",
            "link": "https://example.com/grant",
        },
    )
    assert public.status_code == 201 and public.json() == {"id": row["id"]}


def test_staff_writes_all_append_audit_entries():
    c = client(user("admin"))
    row = create_staff_opportunity(c, status="published", audience="public")
    collection = c.post(
        "/api/admin/collections", json={"slug": "test", "title": "Test"}
    ).json()
    assert (
        c.patch(
            f"/api/admin/collections/{collection['id']}", json={"title": "Updated"}
        ).status_code
        == 200
    )
    assert c.delete(f"/api/admin/collections/{collection['id']}").status_code == 200
    assert c.put("/api/admin/site", json={"hero_title": "Updated"}).status_code == 200
    assert (
        c.put(
            "/api/admin/settings", json=c.get("/api/admin/settings").json()
        ).status_code
        == 200
    )
    assert (
        c.post("/api/admin/scans", json={"categories": ["startup"]}).status_code == 200
    )
    assert (
        client()
        .post(
            f"/api/public/opportunities/{row['slug']}/report",
            json={"reason": "Check this"},
        )
        .status_code
        == 202
    )
    report = c.get("/api/admin/reports").json()[0]
    assert (
        c.patch(
            f"/api/admin/reports/{report['id']}", json={"resolved": True}
        ).status_code
        == 200
    )
    actions = {
        a["action"]
        for a in c.get("/api/admin/audit", params={"limit": 100}).json()["items"]
    }
    assert {
        "opportunity.create",
        "collection.create",
        "collection.update",
        "collection.delete",
        "site.update",
        "settings.update",
        "scan.create",
        "report.resolve",
    } <= actions


def test_reverify_worker_reads_only_target_and_retains_hidden_status(monkeypatch):
    from api import web
    from api.agent import orchestrator
    from api.agent.llm.base import LLMResponse, ToolCall
    from api.scans import queue
    from api.scans.models import TaskStatus

    url = "https://example.com/climate"
    row = add(status="hidden", source_url=url)
    c = client(user("editor"))
    scan_id = c.post(f"/api/admin/opportunities/{row['id']}/reverify").json()["scan_id"]

    class Verifier:
        def __init__(self):
            self.turn = 0

        async def chat(self, messages, system, tools, max_tokens=4096):
            self.turn += 1
            if self.turn == 1:
                return LLMResponse(
                    tool_calls=[
                        ToolCall(id="fetch", name="fetch_page", arguments={"url": url})
                    ]
                )
            if self.turn == 2:
                return LLMResponse(
                    tool_calls=[
                        ToolCall(
                            id="wrong",
                            name="save_opportunity",
                            arguments={
                                "title": "Different Grant",
                                "organization": "",
                                "category": "startup",
                                "source_url": url,
                            },
                        )
                    ]
                )
            if self.turn == 3:
                return LLMResponse(
                    tool_calls=[
                        ToolCall(
                            id="save",
                            name="save_opportunity",
                            arguments={
                                "title": "Climate Grant",
                                "organization": "",
                                "category": "startup",
                                "source_url": url,
                                "eligibility": "Ghanaian founders",
                            },
                        )
                    ]
                )
            return LLMResponse(text="Verified the Climate Grant.")

    async def fetch(url, max_chars=None, offset=0, **kwargs):
        return "Climate Grant is open to Ghanaian founders."

    model = Verifier()
    monkeypatch.setattr(web, "fetch_page", fetch)
    monkeypatch.setattr(orchestrator, "get_provider", lambda **kwargs: model)

    async def process():
        async with SessionLocal() as session:
            task = (
                await session.execute(
                    select(ScanTask).where(ScanTask.scan_id == scan_id)
                )
            ).scalar_one()
            task.status = TaskStatus.running
            await session.commit()
            await queue.process_claimed(session, task)
        async with SessionLocal() as session:
            tasks = (
                (
                    await session.execute(
                        select(ScanTask).where(ScanTask.scan_id == scan_id)
                    )
                )
                .scalars()
                .all()
            )
            count = (await session.execute(select(Opportunity))).scalars().all()
            return tasks, count

    tasks, rows = run(process())
    assert len(rows) == 1 and rows[0].status == "hidden"
    assert (
        rows[0].eligibility == "Ghanaian founders" and rows[0].verified_at is not None
    )
    assert tasks[0].status == TaskStatus.done
    detail = c.get(f"/api/admin/opportunities/{row['id']}").json()
    assert detail["history"][0]["action"] == "opportunity.reverify"
    assert detail["trace_excerpt"] == "Climate Grant is open to Ghanaian founders."
    assert "Only the requested opportunity" in tasks[0].log


def test_editors_manage_sources_and_every_write_is_audited(monkeypatch):
    from api.core import egress
    from api.opportunities.crawl_models import Source

    async def public_url(value):
        return value

    monkeypatch.setattr(egress, "check_url", public_url)
    editor = user("editor")
    member = user("member")
    assert client(member).get("/api/admin/sources").status_code == 403
    staff = client(editor)
    response = staff.post(
        "/api/admin/sources",
        json={
            "url": "https://fund.example.org/rss",
            "kind": "rss",
            "category_hints": ["student"],
        },
    )
    assert response.status_code == 201, response.text
    source = response.json()
    assert source["created_at"].endswith("Z")
    assert (
        staff.patch(
            f"/api/admin/sources/{source['id']}",
            json={
                "url": "https://fund.example.org/feed",
                "kind": "rss",
                "enabled": True,
                "category_hints": ["research"],
            },
        ).status_code
        == 200
    )
    assert staff.post(f"/api/admin/sources/{source['id']}/crawl").status_code == 202
    assert read(Source, source["id"]).crawl_requested
    assert (
        staff.patch(
            f"/api/admin/sources/{source['id']}", json={"enabled": False}
        ).status_code
        == 200
    )
    assert staff.post(f"/api/admin/sources/{source['id']}/crawl").status_code == 400
    assert (
        staff.patch(
            f"/api/admin/sources/{source['id']}", json={"url": None}
        ).status_code
        == 400
    )
    assert staff.delete(f"/api/admin/sources/{source['id']}").status_code == 204

    async def actions():
        async with SessionLocal() as session:
            return list(
                (
                    await session.execute(
                        select(m.AuditLog.action)
                        .where(m.AuditLog.entity_id == source["id"])
                        .order_by(m.AuditLog.at)
                    )
                ).scalars()
            )

    assert run(actions()) == [
        "source.create",
        "source.update",
        "source.crawl",
        "source.update",
        "source.delete",
    ]


def test_old_settings_client_preserves_crawler_settings():
    staff = client(user("admin"))
    values = staff.get("/api/admin/settings").json()
    values["crawler"]["max_candidates_per_task"] = 3
    assert staff.put("/api/admin/settings", json=values).status_code == 200
    values.pop("crawler")
    response = staff.put("/api/admin/settings", json=values)
    assert response.status_code == 200
    assert response.json()["crawler"]["max_candidates_per_task"] == 3


def test_scan_targets_exactly_one_audience():
    c = client(user(), "app")
    assert c.post("/api/app/scans", json={}).status_code == 422
    assert c.post("/api/app/scans", json={"categories": ["startup", "student"]}).status_code == 422
