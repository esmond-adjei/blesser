import asyncio
import json

import pytest

from api.autofill import service
from api.autofill.feedback import page_host
from api.autofill.matcher import deterministic
from api.autofill.schemas import FormField, Page
from api.core.exceptions import UnprocessableError
from tests.test_applicant_kit import kit as kit_fixture
from tests.test_autofill_api import FakeProvider, request
from tests.test_autofill_feedback import feedback_body
from tests.test_extension_auth import connect, extension

pytestmark = pytest.mark.real_auth
kit = kit_fixture


@pytest.mark.parametrize("host", ["localhost", "localhost:5173", "LOCALHOST:5173"])
def test_page_host_accepts_url_host_with_or_without_port(host):
    assert page_host(Page(url="http://localhost:5173/apply", host=host)) == "localhost"


@pytest.mark.parametrize(
    "host", ["localhost:9999", "other.example", "other.example:5173"]
)
def test_page_host_rejects_mismatched_hosts_and_ports(host):
    with pytest.raises(UnprocessableError):
        page_host(Page(url="http://localhost:5173/apply", host=host))


def test_feedback_report_and_fill_accept_host_with_port(kit):
    client = kit[0]
    client.put("/api/app/profile", json={"given_name": "Ama", "family_name": "Mensah"})
    ext = extension(connect(client))
    feedback = feedback_body(corrected={"value": "Edited name"})
    feedback["page"] = {"url": "http://localhost:5173/apply", "host": "localhost:5173"}
    assert ext.post("/api/app/autofill/feedback", json=feedback).status_code == 204
    report = {
        "page": {"url": "http://localhost:5173/apply", "host": "localhost:5173"},
        "fields": [],
        "note": "Problem",
    }
    assert ext.post("/api/app/autofill/reports", json=report).status_code == 204
    for feedback_host in ("localhost", "localhost:5173"):
        feedback["page"]["host"] = feedback_host
        assert ext.post("/api/app/autofill/feedback", json=feedback).status_code == 204
        for host in ("localhost", "localhost:5173"):
            body = request([{"key": "f", "label": "Full name"}], allow_drafting=False)
            body["page"] = {"url": "http://localhost:5173/apply", "host": host}
            response = client.post("/api/app/autofill/fill", json=body)
            assert response.status_code == 200
            assert (
                response.json()["fills"][0]["value"],
                response.json()["fills"][0]["rule"],
            ) == ("Edited name", "correction")
    ext.close()


def test_concept_and_inference_notes_explain_the_source_and_option():
    gender = FormField(
        key="g",
        label="Gender",
        type="radio",
        options=[{"label": "Man", "value": "m"}, {"label": "Woman", "value": "w"}],
    )
    result = deterministic(gender, {"gender": "Male"}, {}, {})
    assert (result.value, result.rule, result.note) == (
        "m",
        "concept:gender",
        "Matched 'Male' to 'Man'",
    )
    birth = deterministic(
        FormField(key="b", label="Country of birth"),
        {"nationality": "Ghanaian"},
        {},
        {},
    )
    assert (birth.value, birth.rule, birth.note) == (
        "Ghana",
        "inferred:nationality",
        "From your nationality 'Ghanaian'",
    )


def test_note_never_exposes_a_secret_from_an_option_label_or_inference():
    secret = {"passport_number": "P1234567"}
    gender = FormField(
        key="g",
        label="Gender",
        type="radio",
        options=[{"label": "Man P1234567", "value": "m"}],
    )
    result = deterministic(gender, {"gender": "Male"}, {}, secret)
    assert result.rule == "concept:gender"
    assert "P1234567" not in result.note
    role = FormField(key="r", label="Current role")
    result = deterministic(
        role,
        {"experience": [{"current": True, "role": "Engineer P1234567"}]},
        {},
        secret,
    )
    assert result is None


def test_parenthetical_does_not_enable_sensitive_or_blocked_fields():
    secret = {"passport_number": "P1234567"}
    for label in (
        "Passport number (optional)",
        "Describe your passport number (if different)",
        "Consent (as on your passport)",
    ):
        assert (
            deterministic(
                FormField(key="f", label=label), {"nationality": "Ghanaian"}, {}, secret
            )
            is None
        )


def test_parenthetical_record_qualifiers_are_retained():
    result = deterministic(
        FormField(key="f", label="Country (Institution)"),
        {"country_of_residence": "Canada", "education": [{"country": "Nigeria"}]},
        {},
        {},
    )
    assert result.value == "Nigeria"


def test_choice_fallback_uses_cleaned_question_without_sensitive_context(monkeypatch):
    provider = FakeProvider('{"g":"m"}')
    monkeypatch.setattr(service, "get_provider", lambda: provider)
    target = FormField(
        key="g",
        label="Gender (as on your passport)",
        type="radio",
        options=[{"label": "Man", "value": "m"}],
    )
    profile = {"gender": "I identify as a man"}
    result = asyncio.run(
        service.draft([target], profile, {}, {"passport_number": "P1234567"})
    )
    assert [(item.value, item.rule) for item in result] == [("m", "model:choice")]
    payload = json.loads(provider.calls[0]["messages"][0]["content"])
    assert payload["fields"][0]["question"] == "Gender"
    assert "passport" not in json.dumps(payload).lower()
    assert "P1234567" not in json.dumps(payload)


@pytest.mark.parametrize(
    "suffix",
    [
        " (as on your passport)",
        " (if different)",
        " (optional)",
        " *",
        " required",
        " (required)",
    ],
)
@pytest.mark.parametrize(
    "label,value",
    [
        ("Country of birth", "Ghana"),
        ("First name", "Ama"),
        ("Email", "ama@example.com"),
        ("Country of institution", "Nigeria"),
    ],
)
def test_common_label_suffixes_do_not_change_intent(label, value, suffix):
    profile = {
        "nationality": "Ghanaian",
        "given_name": "Ama",
        "email": "ama@example.com",
        "education": [{"institution": "University", "country": "Nigeria"}],
    }
    result = deterministic(
        FormField(key="f", label=label + suffix),
        profile,
        {},
        {"passport_number": "P1234567"},
    )
    assert result is not None
    assert result.value == value
    assert "P1234567" not in result.note


@pytest.mark.parametrize(
    "placeholder,expected",
    [
        ("Please input date (M/d/yyyy)", "4/9/1997"),
        ("DD/MM/YYYY", "09/04/1997"),
        ("dd.mm.yy", "09.04.97"),
        ("yyyy-mm-dd", "1997-04-09"),
        ("", "1997-04-09"),
    ],
)
def test_date_follows_placeholder_format(placeholder, expected):
    from api.autofill.matcher import format_date
    from api.autofill.schemas import FormField

    field = FormField(key="f", label="Date of birth", placeholder=placeholder)
    assert format_date("1997-04-09", field) == expected


def test_unhandled_errors_keep_cors_headers():
    from fastapi.testclient import TestClient

    from api.main import app

    @app.get("/__boom_for_test")
    async def boom():
        raise RuntimeError("boom")

    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/__boom_for_test", headers={"Origin": "chrome-extension://abc"}
        )
        assert response.status_code == 500
        assert response.headers["access-control-allow-origin"] == "*"
        assert response.json()["detail"].startswith("Something went wrong")
    finally:
        app.router.routes[:] = [
            r for r in app.router.routes if getattr(r, "path", "") != "/__boom_for_test"
        ]
