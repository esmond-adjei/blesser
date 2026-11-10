import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, text

from api.auth.models import User
from api.auth.security import issue_access_token
from api.autofill import service
from api.autofill.models import Correction, FormReport
from api.core.db import SessionLocal
from tests.test_applicant_kit import kit as kit_fixture
from tests.test_applicant_kit import rows, run
from tests.test_autofill_api import FakeProvider, fill, request
from tests.test_extension_auth import connect, extension

pytestmark = pytest.mark.real_auth
kit = kit_fixture


def feedback_body(field=None, corrected=None):
    return {
        "page": {"url": "https://forms.example.com/apply", "host": "forms.example.com"},
        "field": field or {"key": "f", "label": "Full name", "type": "text"},
        "filled": {
            "value": "Original",
            "source": "profile",
            "rule": "matched:full_name",
        },
        "corrected": corrected or {"value": "Correction"},
    }


def test_corrections_latest_wins_normalized_label_type_host_and_ownership(kit):
    client, other, ids, _ = kit
    client.put("/api/app/profile", json={"given_name": "Ama", "family_name": "Mensah"})
    ext = extension(connect(client))
    body = feedback_body()
    assert ext.post("/api/app/autofill/feedback", json=body).status_code == 204
    result = fill(client, [{"key": "new", "label": "FULL NAME!"}], allow_drafting=False)
    assert [(row["value"], row["rule"]) for row in result["fills"]] == [
        ("Correction", "correction")
    ]
    body["corrected"] = {"value": "Latest"}
    body["field"]["label"] = "Full NAME!"
    assert ext.post("/api/app/autofill/feedback", json=body).status_code == 204
    response = client.get("/api/app/autofill/corrections")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    saved = response.json()
    assert len(saved) == 1
    assert set(saved[0]) == {
        "id",
        "host",
        "label",
        "field_type",
        "value",
        "wrong_field",
        "updated_at",
    }
    assert (saved[0]["host"], saved[0]["value"], saved[0]["wrong_field"]) == (
        "forms.example.com",
        "Latest",
        False,
    )
    assert other.get("/api/app/autofill/corrections").json() == []
    assert (
        other.delete(f"/api/app/autofill/corrections/{saved[0]['id']}").status_code
        == 404
    )
    assert (
        fill(other, [{"key": "f", "label": "Full name"}], allow_drafting=False)["fills"]
        == []
    )
    body = request([{"key": "f", "label": "Full name"}], allow_drafting=False)
    body["page"] = {
        "url": "https://other.example.com/apply",
        "host": "other.example.com",
    }
    assert (
        client.post("/api/app/autofill/fill", json=body).json()["fills"][0]["value"]
        == "Ama Mensah"
    )
    assert (
        fill(
            client,
            [{"key": "f", "label": "Full name", "type": "search"}],
            allow_drafting=False,
        )["fills"][0]["value"]
        == "Ama Mensah"
    )
    assert len(rows(Correction, ids[0])) == 1
    assert (
        client.delete(f"/api/app/autofill/corrections/{saved[0]['id']}").status_code
        == 204
    )
    assert (
        fill(client, [{"key": "f", "label": "Full name"}], allow_drafting=False)[
            "fills"
        ][0]["value"]
        == "Ama Mensah"
    )
    ext.close()


@pytest.mark.parametrize(
    "corrected", [{"wrong_field": True}, {"value": None}, {"value": ""}, {"value": []}]
)
def test_cleared_or_wrong_field_corrections_suppress_every_match_stage(
    kit, monkeypatch, corrected
):
    client = kit[0]
    client.put("/api/app/profile", json={"short_bio": "Known bio", "given_name": "Ama"})
    client.post(
        "/api/app/answers",
        json={"question": "Explain your background", "answer": "Saved background"},
    )
    provider = FakeProvider('{"f":"Do not refill"}')
    monkeypatch.setattr(service, "get_provider", lambda: provider)
    target = {"key": "f", "label": "Explain your background", "tag": "textarea"}
    ext = extension(connect(client))
    body = feedback_body(target, corrected)
    assert ext.post("/api/app/autofill/feedback", json=body).status_code == 204
    result = fill(client, [target])
    assert result["fills"] == []
    assert result["unfilled"] == [
        {"key": "f", "reason": "Your correction leaves this field for you"}
    ]
    assert provider.calls == []
    ext.close()


def test_correction_options_limits_and_blocked_fields(kit):
    client = kit[0]
    ext = extension(connect(client))
    target = {
        "key": "gender",
        "label": "Gender",
        "type": "radio",
        "options": [{"label": "Man", "value": "m"}, {"label": "Woman", "value": "f"}],
    }
    assert (
        ext.post(
            "/api/app/autofill/feedback", json=feedback_body(target, {"value": "Male"})
        ).status_code
        == 204
    )
    assert fill(client, [target], allow_drafting=False)["fills"][0]["value"] == "m"
    target["options"] = [{"label": "Different", "value": "other"}]
    assert fill(client, [target], allow_drafting=False)["fills"] == []
    for target in [
        {"key": "f", "label": "Full name", "max_length": 2},
        {"key": "f", "label": "Password", "type": "password"},
        {"key": "f", "label": "Consent", "type": "checkbox"},
    ]:
        assert (
            ext.post(
                "/api/app/autofill/feedback",
                json=feedback_body(target, {"value": "Unsafe"}),
            ).status_code
            == 204
        )
        assert fill(client, [target], allow_drafting=False)["fills"] == []
    ext.close()


def test_correction_values_are_encrypted_and_not_shared_with_model(kit, monkeypatch):
    client, _, ids, _ = kit
    client.put("/api/app/profile", json={"short_bio": "I write code."})
    ext = extension(connect(client))
    body = feedback_body(corrected={"value": "MEMBER-PRIVATE-EDIT"})
    body["filled"]["value"] = "ORIGINAL-PRIVATE-VALUE"
    assert ext.post("/api/app/autofill/feedback", json=body).status_code == 204

    async def raw_values():
        async with SessionLocal() as session:
            return (
                await session.execute(
                    text(
                        "SELECT value, filled FROM autofill_corrections WHERE user_id = :user_id"
                    ),
                    {"user_id": ids[0]},
                )
            ).one()

    encrypted = str(run(raw_values()))
    assert (
        "MEMBER-PRIVATE-EDIT" not in encrypted
        and "ORIGINAL-PRIVATE-VALUE" not in encrypted
    )
    provider = FakeProvider('{"draft":"I write code."}')
    monkeypatch.setattr(service, "get_provider", lambda: provider)
    fill(client, [{"key": "draft", "label": "Explain your work", "tag": "textarea"}])
    assert "PRIVATE" not in json.dumps(provider.calls)
    ext.close()


def test_feedback_and_reports_require_ext_and_corrections_require_app(kit):
    client = kit[0]
    ext = extension(connect(client))
    assert (
        client.post("/api/app/autofill/feedback", json=feedback_body()).status_code
        == 401
    )
    assert (
        client.post(
            "/api/app/autofill/reports",
            json={
                "page": {"url": "https://example.com"},
                "fields": [],
                "note": "Problem",
            },
        ).status_code
        == 401
    )
    assert ext.get("/api/app/autofill/corrections").status_code == 401
    assert ext.delete("/api/app/autofill/corrections/missing").status_code == 401
    body = feedback_body()
    body["page"]["host"] = "forged.example.com"
    assert ext.post("/api/app/autofill/feedback", json=body).status_code == 422
    body = feedback_body()
    body["corrected"] = {"wrong_field": False}
    assert ext.post("/api/app/autofill/feedback", json=body).status_code == 422
    ext.close()


def test_reports_are_descriptors_only_bounded_and_staff_only(kit):
    client, _, ids, _ = kit
    ext = extension(connect(client))
    body = {
        "page": {
            "url": "https://forms.example.com/apply",
            "host": "forms.example.com",
            "title": "Application",
        },
        "fields": [
            {
                "key": "gender",
                "label": "Gender",
                "options": [{"label": "Man", "value": "man"}],
            }
        ],
        "note": "The gender did not match.",
    }
    response = ext.post("/api/app/autofill/reports", json=body)
    assert response.status_code == 204
    assert len(rows(FormReport, ids[0])) == 1
    unsafe = copy.deepcopy(body)
    unsafe["fields"][0]["value"] = "PERSONAL-VALUE"
    assert ext.post("/api/app/autofill/reports", json=unsafe).status_code == 422
    unsafe = copy.deepcopy(body)
    unsafe["fields"] *= 301
    assert ext.post("/api/app/autofill/reports", json=unsafe).status_code == 422
    unsafe["fields"] = [{"key": str(i), "label": "x" * 4000} for i in range(70)]
    assert ext.post("/api/app/autofill/reports", json=unsafe).status_code == 422
    assert client.get("/api/admin/autofill-reports").status_code == 401
    assert ext.get("/api/admin/autofill-reports").status_code == 401

    async def promote():
        async with SessionLocal() as session:
            user = await session.get(User, ids[0])
            user.role = "editor"
            await session.commit()

    run(promote())
    with TestClient(
        client.app,
        headers={"Authorization": f"Bearer {issue_access_token(ids[0], 'admin')}"},
    ) as staff:
        response = staff.get("/api/admin/autofill-reports?limit=1&offset=0")
        assert response.status_code == 200, response.text
        report = response.json()[0]
        assert set(report) == {"id", "page", "fields", "note", "created_at"}
        assert report["fields"][0]["options"][0]["value"] == "man"
        assert "PERSONAL-VALUE" not in json.dumps(report)
        assert staff.get("/api/admin/autofill-reports?limit=101").status_code == 422
    ext.close()


def test_feedback_and_reports_cascade_on_account_deletion(kit):
    client, _, ids, _ = kit
    ext = extension(connect(client))
    assert (
        ext.post("/api/app/autofill/feedback", json=feedback_body()).status_code == 204
    )
    assert (
        ext.post(
            "/api/app/autofill/reports",
            json={
                "page": {"url": "https://example.com"},
                "fields": [],
                "note": "Problem",
            },
        ).status_code
        == 204
    )

    async def remove():
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.id == ids[0]))
            await session.commit()

    run(remove())
    assert rows(Correction, ids[0]) == rows(FormReport, ids[0]) == []
    ext.close()


def test_choice_fallback_shares_one_drafting_call_and_uses_relevant_fact(
    kit, monkeypatch
):
    client = kit[0]
    client.put(
        "/api/app/profile",
        json={"short_bio": "I build useful tools.", "email": "private@example.com"},
    )
    project_id = client.post(
        "/api/app/projects",
        json={"name": "Project", "sector": "Software for crop farmers"},
    ).json()["id"]
    provider = FakeProvider(
        '{"choice":"ag","checks":"ag","draft":"I build useful tools.","unknown":"ag"}'
    )
    monkeypatch.setattr(service, "get_provider", lambda: provider)
    choice = {
        "key": "choice",
        "label": "Sector",
        "tag": "select",
        "options": [
            {"label": "Agriculture", "value": "ag"},
            {"label": "Banking", "value": "bank"},
        ],
    }
    fields = [
        choice,
        {**choice, "key": "checks", "type": "checkbox"},
        {"key": "draft", "label": "Explain your work", "tag": "textarea"},
        {**choice, "key": "unknown", "label": "Visa eligibility"},
    ]
    result = fill(client, fields, project_id)
    assert [(row["key"], row["value"], row["rule"]) for row in result["fills"]] == [
        ("choice", "ag", "model:choice"),
        ("checks", ["ag"], "model:choice"),
        ("draft", "I build useful tools.", "model:draft"),
    ]
    assert result["usage"] == {"drafted_fields": 3, "remaining_today": 57}
    assert len(provider.calls) == 1
    payload = json.loads(provider.calls[0]["messages"][0]["content"])
    assert [row["key"] for row in payload["fields"]] == ["choice", "checks", "draft"]
    assert payload["fields"][0]["task"] == "choose_one_option_or_null"
    assert payload["fields"][0]["facts"] == {"sector": "Software for crop farmers"}
    assert payload["fields"][0]["options"] == choice["options"]
    assert "private@example.com" not in json.dumps(payload["fields"][0])


@pytest.mark.parametrize(
    "answer", ["Agriculture", "not-an-option", None, ["ag"], 42, {"value": "ag"}]
)
def test_choice_model_rejects_anything_except_an_exact_option_value(
    kit, monkeypatch, answer
):
    client = kit[0]
    project_id = client.post(
        "/api/app/projects",
        json={"name": "Project", "sector": "Software for crop farmers"},
    ).json()["id"]
    provider = FakeProvider(json.dumps({"choice": answer}))
    monkeypatch.setattr(service, "get_provider", lambda: provider)
    choice = {
        "key": "choice",
        "label": "Sector",
        "tag": "select",
        "options": [{"label": "Agriculture", "value": "ag"}],
    }
    assert fill(client, [choice], project_id, allow_drafting=False)["fills"] == []
    assert provider.calls == []
    result = fill(client, [choice], project_id)
    assert result["fills"] == []
    assert result["usage"] == {"drafted_fields": 0, "remaining_today": 59}
    payload = json.loads(provider.calls[0]["messages"][0]["content"])
    assert payload["facts"] == {}


def test_sensitive_choice_fields_never_reach_model(kit, monkeypatch):
    client = kit[0]
    client.put(
        "/api/app/profile",
        json={"short_bio": "Code", "sensitive": {"passport_number": "SECRET123"}},
    )
    provider = FakeProvider("{}")
    monkeypatch.setattr(service, "get_provider", lambda: provider)
    fill(
        client,
        [
            {
                "key": "passport",
                "label": "Passport number",
                "options": [{"label": "Other", "value": "other"}],
            }
        ],
    )
    assert provider.calls == []


def test_concurrent_feedback_upserts_one_mapping_then_latest_replaces_it(kit):
    client = kit[0]
    ext = extension(connect(client))
    bodies = [
        feedback_body(corrected={"value": value}) for value in ("First", "Second")
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda body: ext.post("/api/app/autofill/feedback", json=body), bodies
            )
        )
    assert [response.status_code for response in responses] == [204, 204]
    saved = client.get("/api/app/autofill/corrections").json()
    assert len(saved) == 1
    assert saved[0]["value"] in {"First", "Second"}
    assert (
        ext.post(
            "/api/app/autofill/feedback",
            json=feedback_body(corrected={"value": "Latest"}),
        ).status_code
        == 204
    )
    assert client.get("/api/app/autofill/corrections").json()[0]["value"] == "Latest"
    ext.close()


def test_owner_failures_through_profile_and_fill_routes(kit):
    client = kit[0]
    response = client.put(
        "/api/app/profile",
        json={
            "gender": "Male",
            "nationality": "Ghanaian",
            "country_of_residence": "Canada",
            "education": [{"institution": "University of Ghana", "country": "Ghana"}],
        },
    )
    assert response.status_code == 200
    assert (
        response.json()["country_of_birth"] == response.json()["place_of_birth"] == ""
    )
    result = fill(
        client,
        [
            {
                "key": "gender",
                "label": "Gender",
                "type": "radio",
                "options": [
                    {"label": value, "value": value}
                    for value in ("Man", "Woman", "Non-binary", "Prefer not to say")
                ],
            },
            {"key": "institution", "label": "Country of Institution"},
            {"key": "birth-text", "label": "Country of birth"},
            {
                "key": "birth-select",
                "label": "Country of birth",
                "tag": "select",
                "options": [{"label": "Ghana", "value": "Ghana"}],
            },
        ],
        allow_drafting=False,
    )
    assert [
        (row["key"], row["value"], row["rule"], row["confidence"])
        for row in result["fills"]
    ] == [
        ("gender", "Man", "concept:gender", "high"),
        ("institution", "Ghana", "qualifier:education.country", "high"),
        ("birth-text", "Ghana", "inferred:nationality", "medium"),
        ("birth-select", "Ghana", "inferred:nationality", "medium"),
    ]
