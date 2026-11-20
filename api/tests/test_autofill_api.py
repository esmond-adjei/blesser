import asyncio
import copy
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import delete

from api.agent.llm.base import LLMResponse
from api.applicant_kit.models import Answer
from api.applications.models import Application
from api.autofill import service
from api.autofill.models import DailyUsage
from api.core.config import settings
from api.core.db import SessionLocal
from api.opportunities.models import Opportunity
from tests.test_applicant_kit import kit as kit_fixture
from tests.test_applicant_kit import rows, run, upload

pytestmark = pytest.mark.real_auth
kit = kit_fixture
FIXTURES = Path(__file__).parent / "fixtures" / "autofill"
KIT = json.loads((FIXTURES / "kit.json").read_text())


class FakeProvider:
    def __init__(self, output=None, *, truncated=False, error=False):
        self.calls = []
        self.output = output
        self.truncated = truncated
        self.error = error

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise TimeoutError("provider unavailable")
        return LLMResponse(text=self.output, truncated=self.truncated)


@pytest.fixture
def saved_kit(kit):
    client = kit[0]
    response = client.put("/api/app/profile", json=KIT["profile"])
    assert response.status_code == 200, response.text
    response = client.post("/api/app/projects", json=KIT["project"])
    assert response.status_code == 201, response.text
    return kit, response.json()["id"]


def request(fields, project_id=None, **kwargs):
    return {
        "page": {
            "url": "https://forms.example.com/apply",
            "title": "Application",
            "host": "forms.example.com",
        },
        "use": {"profile": True, "project_id": project_id},
        "fields": fields,
        **kwargs,
    }


def fill(client, fields, project_id=None, **kwargs):
    response = client.post(
        "/api/app/autofill/fill", json=request(fields, project_id, **kwargs)
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    return response.json()


def test_cheapest_first_one_batched_call_and_usage(saved_kit, monkeypatch):
    kit, project_id = saved_kit
    client = kit[0]
    document = upload(client, is_default="true").json()
    answer = client.post(
        "/api/app/answers",
        json={
            "question": "Why this fellowship?",
            "answer": "I build useful software.",
            "project_id": project_id,
        },
    ).json()
    provider = FakeProvider(
        json.dumps(
            {
                "draft-a": "I build tools for small businesses.",
                "draft-b": "Siwa helps shop owners manage stock.",
            }
        )
    )
    monkeypatch.setattr(service, "get_provider", lambda: provider)
    fields = [
        {"key": "name", "label": "Full name"},
        {"key": "company", "label": "Startup name"},
        {"key": "cv", "label": "CV", "type": "file", "accept": ".pdf"},
        {"key": "saved", "label": answer["question"], "tag": "textarea"},
        {
            "key": "draft-a",
            "label": "Explain how your background prepared you.",
            "tag": "textarea",
            "word_limit": 20,
        },
        {
            "key": "draft-b",
            "label": "How would this support your work?",
            "tag": "textarea",
            "max_length": 100,
        },
        {"key": "unfilled", "label": "Audited profit in 2023", "type": "number"},
    ]
    result = fill(client, fields, project_id)
    assert [
        (row["key"], row["source"], row["value"], row["document_id"])
        for row in result["fills"]
    ] == [
        ("name", "profile", "Ama Mensah", None),
        ("company", "project", "Siwa", None),
        ("cv", "document", None, document["id"]),
        ("saved", "answer", "I build useful software.", None),
        ("draft-a", "drafted", "I build tools for small businesses.", None),
        ("draft-b", "drafted", "Siwa helps shop owners manage stock.", None),
    ]
    assert [row["key"] for row in result["unfilled"]] == ["unfilled"]
    assert result["usage"] == {"drafted_fields": 2, "remaining_today": 58}
    assert len(provider.calls) == 1
    payload = json.loads(provider.calls[0]["messages"][0]["content"])
    assert [field["key"] for field in payload["fields"]] == ["draft-a", "draft-b"]
    assert payload["fields"][0]["word_limit"] == 20
    assert payload["facts"]["project"]["name"] == "Siwa"
    assert "never invent" in provider.calls[0]["system"].lower()


def test_no_drafting_when_disallowed_or_no_selected_context(saved_kit, monkeypatch):
    kit, project_id = saved_kit
    provider = FakeProvider('{"f":"Should not be called"}')
    monkeypatch.setattr(service, "get_provider", lambda: provider)
    field = {"key": "f", "tag": "textarea", "label": "Explain your background."}
    result = fill(kit[0], [field], project_id, allow_drafting=False)
    assert result["usage"] == {"drafted_fields": 0, "remaining_today": 60}
    body = request([field])
    body["use"]["profile"] = False
    assert kit[0].post("/api/app/autofill/fill", json=body).json()["fills"] == []
    assert provider.calls == []


def test_model_context_respects_selection_and_does_not_send_other_projects(
    saved_kit, monkeypatch
):
    kit, project_id = saved_kit
    kit[0].post("/api/app/projects", json={"name": "EXCLUDED-OTHER-PROJECT"})
    provider = FakeProvider('{"f":"Safe answer"}')
    monkeypatch.setattr(service, "get_provider", lambda: provider)
    body = request(
        [{"key": "f", "tag": "textarea", "label": "Explain your approach."}], project_id
    )
    body["use"]["profile"] = False
    assert kit[0].post("/api/app/autofill/fill", json=body).status_code == 200
    payload = json.loads(provider.calls[0]["messages"][0]["content"])
    assert "profile" not in payload["facts"]
    assert payload["facts"]["project"]["name"] == "Siwa"
    assert KIT["profile"]["email"] not in json.dumps(
        payload["facts"].get("profile", {})
    )
    assert "EXCLUDED-OTHER-PROJECT" not in json.dumps(provider.calls)


@pytest.mark.parametrize(
    "output,truncated,error",
    [
        (
            '{"good":"Safe answer","long":"one two three","chars":"abcdef","number":42,"nested":{},"blank":"  ","null":null,"unknown":"must not appear"}',
            False,
            False,
        ),
        ("not JSON", False, False),
        ('["invalid"]', False, False),
        ('{"good":"Safe answer"}', True, False),
        ("{}", False, True),
    ],
)
def test_drafts_drop_invalid_values_and_charge_attempts(
    saved_kit, monkeypatch, output, truncated, error
):
    kit, project_id = saved_kit
    provider = FakeProvider(output, truncated=truncated, error=error)
    monkeypatch.setattr(service, "get_provider", lambda: provider)
    fields = [
        {"key": key, "label": "Explain your motivation.", "tag": "textarea"}
        for key in ("good", "long", "chars", "number", "nested", "blank", "null")
    ]
    fields[1]["word_limit"] = 2
    fields[2]["max_length"] = 5
    result = fill(kit[0], fields, project_id)
    expected = ["good"] if output.startswith('{"good":"Safe answer","long"') else []
    assert [row["key"] for row in result["fills"]] == expected
    assert result["usage"] == {"drafted_fields": len(expected), "remaining_today": 53}


def test_daily_cap_is_per_member_shared_between_requests_and_resets_next_day(
    saved_kit, monkeypatch
):
    kit, project_id = saved_kit
    client, other, ids, _ = kit
    monkeypatch.setattr(settings, "autofill_drafts_per_day", 2)
    provider = FakeProvider('{"a":"Safe answer","b":"Safe answer","c":"Safe answer"}')
    monkeypatch.setattr(service, "get_provider", lambda: provider)
    fields = [
        {"key": key, "label": "Explain your work.", "tag": "textarea"} for key in "abc"
    ]
    assert fill(client, fields, project_id)["usage"] == {
        "drafted_fields": 2,
        "remaining_today": 0,
    }
    assert fill(client, fields, project_id)["usage"] == {
        "drafted_fields": 0,
        "remaining_today": 0,
    }
    assert len(provider.calls) == 1
    other.put("/api/app/profile", json={"short_bio": "I write software."})
    assert fill(other, fields[:1])["usage"] == {
        "drafted_fields": 1,
        "remaining_today": 1,
    }
    assert rows(DailyUsage, ids[0])[0].drafted_fields == 2
    day = service.today()
    monkeypatch.setattr(service, "today", lambda: day + timedelta(days=1))
    assert fill(client, fields[:1], project_id)["usage"]["remaining_today"] == 1


def test_concurrent_requests_cannot_overspend_daily_cap(saved_kit, monkeypatch):
    kit, project_id = saved_kit
    monkeypatch.setattr(settings, "autofill_drafts_per_day", 1)
    provider = FakeProvider('{"f":"Safe answer"}')
    monkeypatch.setattr(service, "get_provider", lambda: provider)
    body = request(
        [{"key": "f", "label": "Explain your work.", "tag": "textarea"}], project_id
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: kit[0].post("/api/app/autofill/fill", json=body), range(2)
            )
        )
    assert [response.status_code for response in responses] == [200, 200]
    assert (
        sum(response.json()["usage"]["drafted_fields"] for response in responses) == 1
    )
    assert len(provider.calls) == 1


def test_sensitive_exact_matches_only_and_absent_from_prompt(saved_kit, monkeypatch):
    kit, project_id = saved_kit
    client = kit[0]
    secrets = KIT["profile"]["sensitive"]
    profile = copy.deepcopy(KIT["profile"])
    profile["long_bio"] += " " + secrets["national_id"]
    profile["short_bio"] = secrets["passport_number"]
    client.put("/api/app/profile", json=profile)
    project = copy.deepcopy(KIT["project"])
    project["custom_fields"] += [
        {"label": "Private code", "value": secrets["passport_number"]},
        {"label": "Passport number", "value": "PRIVATE-SECONDARY-ID"},
    ]
    client.put(f"/api/app/projects/{project_id}", json=project)
    provider = FakeProvider(
        json.dumps({"draft": "safe", "leak": secrets["national_id"]})
    )
    monkeypatch.setattr(service, "get_provider", lambda: provider)
    fields = [
        {"key": "id", "label": "National ID number"},
        {"key": "passport", "label": "Passport number"},
        {"key": "expiry", "label": "Passport expiry date", "type": "date"},
        {"key": "vague", "label": "Describe your passport", "tag": "textarea"},
        {"key": "bio", "label": "Short bio"},
        {"key": "custom", "label": "Private code"},
        {
            "key": "draft",
            "label": "Explain your motivation.",
            "tag": "textarea",
            "help_text": secrets["passport_number"],
        },
        {"key": "leak", "label": "Explain your goals.", "tag": "textarea"},
    ]
    result = fill(client, fields, project_id)
    assert {row["key"]: row["value"] for row in result["fills"]} == {
        "id": secrets["national_id"],
        "passport": secrets["passport_number"],
        "expiry": secrets["passport_expiry"],
        "draft": "safe",
    }
    prompt = json.dumps(provider.calls)
    payload = json.loads(provider.calls[0]["messages"][0]["content"])
    assert payload["facts"]["profile"]["given_name"] == "Ama"
    assert payload["facts"]["project"]["name"] == "Siwa"
    for value in [*secrets.values(), "PRIVATE-SECONDARY-ID"]:
        assert value not in prompt
    body = request(fields, project_id, allow_drafting=False)
    body["use"]["profile"] = False
    assert client.post("/api/app/autofill/fill", json=body).json()["fills"] == []


def test_saved_answers_similarity_limits_scope_and_sensitive_filter(saved_kit):
    kit, project_id = saved_kit
    client, other, ids, _ = kit
    other_project = client.post("/api/app/projects", json={"name": "Other"}).json()[
        "id"
    ]
    for owner, project, question, answer in [
        (
            client,
            project_id,
            "Why do you want this fellowship?",
            "A useful opportunity.",
        ),
        (
            client,
            project_id,
            "Why do you want this fellowship?",
            "This answer is much too long for the input.",
        ),
        (client, other_project, "Why do you want this fellowship?", "Wrong project."),
        (other, None, "Why do you want this fellowship?", "Wrong member."),
        (client, None, "Explain your motivation?", "I enjoy useful work."),
        (
            client,
            None,
            "Explain your private history?",
            KIT["profile"]["sensitive"]["passport_number"],
        ),
    ]:
        response = owner.post(
            "/api/app/answers",
            json={"question": question, "answer": answer, "project_id": project},
        )
        assert response.status_code == 201, response.text
    fields = [
        {
            "key": "saved",
            "label": "Why do you want this fellowship (maximum 50 words)?",
            "tag": "textarea",
            "word_limit": 4,
            "max_length": 25,
        },
        {"key": "global", "label": "Explain your motivation.", "tag": "textarea"},
        {
            "key": "short",
            "label": "Why do you want this fellowship?",
            "tag": "textarea",
            "max_length": 3,
        },
        {"key": "private", "label": "Explain your private history?", "tag": "textarea"},
    ]
    result = fill(client, fields, project_id, allow_drafting=False)
    assert [(row["key"], row["source"], row["value"]) for row in result["fills"]] == [
        ("saved", "answer", "A useful opportunity."),
        ("global", "answer", "I enjoy useful work."),
    ]
    result = fill(client, fields[:1], allow_drafting=False)
    assert result["fills"] == []
    assert all(row.normalized_question for row in rows(Answer, ids[0]))


def test_documents_respect_selected_profile_project_and_accept(saved_kit):
    kit, project_id = saved_kit
    client, other, _, _ = kit
    profile_doc = upload(client, is_default="true").json()
    project_doc = upload(
        client, kind="pitch_deck", is_default="true", project_ids=[project_id]
    ).json()
    upload(other, kind="budget", is_default="true")
    fields = [
        {"key": "cv", "label": "Resume", "type": "file"},
        {
            "key": "deck",
            "label": "Pitch deck",
            "type": "file",
            "accept": "application/pdf",
        },
        {"key": "budget", "label": "Budget", "type": "file"},
        {"key": "incompatible", "label": "Resume", "type": "file", "accept": "image/*"},
    ]
    assert {
        row["document_id"]
        for row in fill(client, fields, project_id, allow_drafting=False)["fills"]
    } == {profile_doc["id"], project_doc["id"]}
    assert [
        row["document_id"]
        for row in fill(client, fields, allow_drafting=False)["fills"]
    ] == [profile_doc["id"]]
    body = request(fields, project_id, allow_drafting=False)
    body["use"]["profile"] = False
    assert [
        row["document_id"]
        for row in client.post("/api/app/autofill/fill", json=body).json()["fills"]
    ] == [project_doc["id"]]
    assert other.post("/api/app/autofill/fill", json=body).status_code == 404


@pytest.mark.parametrize(
    "url,expected",
    [
        (
            "http://www.EXAMPLE.com/apply/?utm_source=mail&fbclid=x#section",
            "example.com/apply",
        ),
        ("https://example.com:443/apply?b=2&a=1&ref=home", "example.com/apply?a=1&b=2"),
        ("https://example.com:8443/apply/", "example.com:8443/apply"),
        ("https://example.com/apply?job=123", "example.com/apply?job=123"),
        ("file:///apply", None),
        ("https://user:password@example.com/apply", None),
        ("garbage", None),
    ],
)
def test_url_normalization(url, expected):
    assert service.normalize_url(url) == expected


def test_url_matching_only_owned_tracked_opportunities(saved_kit):
    kit, _ = saved_kit
    client, other, ids, _ = kit
    opportunity_id = uuid.uuid4().hex

    async def setup():
        async with SessionLocal() as session:
            session.add(
                Opportunity(
                    id=opportunity_id,
                    title="Test grant",
                    category="startup",
                    link="http://www.funder.example.com/apply/?job=1&utm_source=mail",
                    source_url="https://funder.example.com/grant/",
                    dedupe_key=opportunity_id,
                )
            )
            await session.flush()
            session.add(
                Application(
                    user_id=ids[0], opportunity_id=opportunity_id, title="Test grant"
                )
            )
            await session.commit()

    run(setup())
    try:
        for url in (
            "https://funder.example.com/apply?job=1&ref=blesser",
            "http://www.funder.example.com/grant/?gclid=noise",
        ):
            body = request([], allow_drafting=False)
            body["page"]["url"] = url
            assert (
                client.post("/api/app/autofill/fill", json=body).json()[
                    "matched_opportunity_id"
                ]
                == opportunity_id
            )
            assert (
                other.post("/api/app/autofill/fill", json=body).json()[
                    "matched_opportunity_id"
                ]
                is None
            )
        body["page"]["url"] = "https://funder.example.com/apply?job=2"
        assert (
            client.post("/api/app/autofill/fill", json=body).json()[
                "matched_opportunity_id"
            ]
            is None
        )
    finally:

        async def cleanup():
            async with SessionLocal() as session:
                await session.execute(
                    delete(Opportunity).where(Opportunity.id == opportunity_id)
                )
                await session.commit()

        run(cleanup())


def test_page_matches_tracked_applications_without_exact_links(saved_kit):
    kit, _ = saved_kit
    client, other, ids, _ = kit
    opportunity_id = uuid.uuid4().hex
    created = []

    async def setup():
        async with SessionLocal() as session:
            session.add(
                Opportunity(
                    id=opportunity_id,
                    title="Kumasi Founders Fund 2026",
                    category="startup",
                    link="https://founders.example.org/fund",
                    source_url="https://news.example.net/2026/11/kumasi-fund",
                    dedupe_key=opportunity_id,
                )
            )
            await session.flush()
            apps = [
                Application(
                    user_id=ids[0],
                    opportunity_id=opportunity_id,
                    title="Kumasi Founders Fund 2026",
                ),
                # Added by hand: no catalog opportunity behind it.
                Application(
                    user_id=ids[0],
                    title="Accra Women in Tech Fellowship",
                    link="https://fellows.example.com/",
                ),
                Application(
                    user_id=ids[0],
                    title="Siwa Green Grant",
                    link="https://docs.google.com/forms/d/e/FORM1/viewform",
                ),
                Application(
                    user_id=ids[0],
                    title="Jobs board role one",
                    link="https://jobs.example.io/apply?job=1",
                ),
                Application(
                    user_id=ids[0],
                    title="Jobs board role two",
                    link="https://jobs.example.io/apply?job=2",
                ),
            ]
            session.add_all(apps)
            await session.commit()
            created.extend(app.id for app in apps)

    def match(url, title="", who=client):
        response = who.get(
            "/api/app/autofill/match", params={"url": url, "title": title}
        )
        assert response.status_code == 200
        return response.json()

    run(setup())
    founders, fellows, green, _, job_two = created
    try:
        # A form page under the opportunity's link.
        assert match("https://founders.example.org/fund/apply/step-1") == {
            "application_id": founders,
            "opportunity_id": opportunity_id,
        }
        # A hand-added application, matched on its own link's site.
        assert match("https://apply.fellows.example.com/x")["application_id"] is None
        assert (
            match("https://fellows.example.com/2026/form?utm_source=x")[
                "application_id"
            ]
            == fellows
        )
        # Shared form hosts need the form's own address; tracking noise is ignored.
        assert (
            match("https://docs.google.com/forms/d/e/FORM1/viewform?usp=sf_link")[
                "application_id"
            ]
            == green
        )
        assert (
            match("https://docs.google.com/forms/d/e/FORM1/formResponse")[
                "application_id"
            ]
            == green
        )
        assert (
            match("https://docs.google.com/forms/d/e/OTHER/viewform")["application_id"]
            is None
        )
        # Two applications on one site: only the matching job id counts.
        assert (
            match("https://jobs.example.io/apply?job=2&ref=blesser")["application_id"]
            == job_two
        )
        assert match("https://jobs.example.io/apply?job=3")["application_id"] is None
        assert match("https://jobs.example.io/careers")["application_id"] is None
        # An aggregator's article is not the funder's site.
        assert (
            match("https://news.example.net/2026/11/other-story")["application_id"]
            is None
        )
        # A form elsewhere, recognised by its title.
        assert (
            match(
                "https://forms.office.com/r/abc",
                "Kumasi Founders Fund 2026: application",
            )["application_id"]
            == founders
        )
        assert (
            match("https://forms.office.com/r/abc", "Kumasi")["application_id"] is None
        )
        # Another member's applications never match.
        assert (
            match("https://founders.example.org/fund/apply", who=other)[
                "application_id"
            ]
            is None
        )

        body = request([], allow_drafting=False)
        body["page"]["url"] = "https://fellows.example.com/apply"
        filled = client.post("/api/app/autofill/fill", json=body).json()
        assert filled["matched_application_id"] == fellows
        assert filled["matched_opportunity_id"] is None
        assert client.get(
            "/api/app/autofill/match", params={"url": "javascript:alert(1)"}
        ).json() == {"application_id": None, "opportunity_id": None}
    finally:

        async def cleanup():
            async with SessionLocal() as session:
                await session.execute(
                    delete(Application).where(Application.id.in_(created))
                )
                await session.execute(
                    delete(Opportunity).where(Opportunity.id == opportunity_id)
                )
                await session.commit()

        run(cleanup())


@pytest.mark.rate_limits
def test_fill_rate_limit_runs_before_validation_and_is_per_member(
    saved_kit, monkeypatch
):
    from api.core.ratelimit import LIMITS

    kit, _ = saved_kit
    monkeypatch.setitem(LIMITS, "autofill", [(1, 3600)])
    assert fill(kit[0], [], allow_drafting=False)["fills"] == []
    response = kit[0].post("/api/app/autofill/fill", json={})
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0
    assert fill(kit[1], [], allow_drafting=False)["fills"] == []


def test_fill_bounds_and_private_errors(kit):
    for fields in (
        [{"key": str(index)} for index in range(301)],
        [{"key": "f"}, {"key": "f"}],
        [{"key": "f", "label": "x" * 4001}],
    ):
        assert (
            kit[0].post("/api/app/autofill/fill", json=request(fields)).status_code
            == 422
        )
    response = kit[0].post(
        "/api/app/autofill/fill",
        content=b"x",
        headers={"Content-Length": str(1024 * 1024 + 1)},
    )
    assert response.status_code == 413


def test_slow_model_leaves_fields_unfilled(saved_kit, monkeypatch):
    kit, project_id = saved_kit

    class SlowProvider(FakeProvider):
        async def chat(self, **kwargs):
            await asyncio.sleep(5)

    monkeypatch.setattr(service, "get_provider", lambda: SlowProvider())
    monkeypatch.setattr(settings, "autofill_draft_timeout_seconds", 0.05)
    field = {"key": "f", "tag": "textarea", "label": "Explain your background."}
    result = fill(kit[0], [field], project_id)
    assert result["fills"] == [] or all(
        f["source"] != "drafted" for f in result["fills"]
    )
    assert [u["key"] for u in result["unfilled"]] == ["f"]
