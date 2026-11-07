import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, update

from api.agent.llm.base import LLMResponse
from api.auth import models as auth_models
from api.core.config import settings
from api.core.db import SessionLocal
from api.cv import models as cv_models
from api.cv import suggest
from api.main import app
from api.metering import service as metering


@pytest.fixture(autouse=True)
def _clean():
    async def _wipe():
        async with SessionLocal() as session:
            for m in (cv_models.CvSuggestion, cv_models.CvTailoredVersion, cv_models.CvDocument):
                await session.execute(delete(m))
            await session.commit()

    asyncio.run(_wipe())
    yield
    asyncio.run(_wipe())


class _Fake:
    """A provider that answers with `reply` and remembers what it saw."""

    def __init__(self, reply='{"replace": "Rust", "rationale": "Names the language."}', boom=False):
        self.reply, self.boom, self.calls = reply, boom, []

    async def chat(self, messages, system, tools, max_tokens=4096):
        self.calls.append({"messages": messages, "system": system})
        if self.boom:
            raise RuntimeError("no key")
        return LLMResponse(text=self.reply, tool_calls=[], usage={"input_tokens": 10, "output_tokens": 5})


@pytest.fixture
def fake(monkeypatch):
    f = _Fake()
    seen: list[dict] = []

    def factory(**kwargs):
        seen.append(kwargs)
        return f

    monkeypatch.setattr(suggest, "get_provider", factory)
    f.kwargs = seen
    return f


CV = "# Jane Doe\n\n## Skills\n\n- Built tools in Python.\n- Taught Python to 30 students.\n"


def _doc(client, markdown=CV, headers=None):
    r = client.post("/api/cv/documents/text", json={"title": "CV", "markdown": markdown}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _utf16(text: str, index: int) -> int:
    return len(text[:index].encode("utf-16-le")) // 2


def _ask(client, doc, text, start, end, headers=None, **extra):
    body = {
        "base_revision": doc["revision"],
        "range": {"from": _utf16(text, start), "to": _utf16(text, end)},
        "text": text[start:end],
        "action": "improve",
        **extra,
    }
    return client.post(f"/api/cv/documents/{doc['id']}/suggest", json=body, headers=headers)


def test_a_suggestion_is_bound_to_the_selected_occurrence(fake):
    with TestClient(app) as client:
        doc = _doc(client)
        second = CV.index("Python", CV.index("Python") + 1)
        r = _ask(client, doc, CV, second, second + len("Python"))
        assert r.status_code == 200, r.text
        [s] = r.json()
        # "Python" occurs twice: the find widens to its line, so it is unique.
        assert s["find"] == "- Taught Python to 30 students."
        assert s["replace"] == "- Taught Rust to 30 students."
        assert s["status"] == "pending" and s["applicable"] and s["created_by"] == "editor"
        assert s["rationale"] == "Names the language."
        assert s["claim_check"]["new_terms"] == ["rust"]
        prompt = fake.calls[0]["messages"][0]["content"]
        assert "<passage>\nPython\n</passage>" in prompt and "Built tools in Python" in prompt

        listed = client.get(f"/api/cv/suggestions?document_id={doc['id']}&base_only=true").json()
        assert [x["id"] for x in listed] == [s["id"]]

        out = client.post(f"/api/cv/suggestions/{s['id']}/accept", json={"confirm_new_terms": True})
        assert out.status_code == 200, out.text
        assert out.json()["markdown"] == CV.replace("Taught Python", "Taught Rust")


def test_a_unique_selection_is_kept_as_it_is(fake):
    fake.reply = '{"replace": "Led a 4-person team.", "rationale": "Shorter."}'
    text = "# Jane\n\n- Led a team of four people.\n"
    with TestClient(app) as client:
        doc = _doc(client, text)
        start = text.index("Led")
        [s] = _ask(client, doc, text, start, text.index("\n", start)).json()
        assert s["find"] == "Led a team of four people."
        assert s["replace"] == "Led a 4-person team."


def test_stale_text_is_refused_before_any_model_call(fake):
    with TestClient(app) as client:
        doc = _doc(client)
        start = CV.index("Built")
        stale = _ask(client, doc, CV, start, start + 5, base_revision=doc["revision"] - 1)
        assert stale.status_code == 409
        assert stale.json()["detail"]["reason"] == "revision"

        moved = client.post(
            f"/api/cv/documents/{doc['id']}/suggest",
            json={
                "base_revision": doc["revision"],
                "range": {"from": start, "to": start + 5},
                "text": "Taught",
                "action": "improve",
            },
        )
        assert moved.status_code == 409 and moved.json()["detail"]["reason"] == "range"

        past = _ask(client, doc, CV, start, start + 5, range={"from": 0, "to": 10_000})
        assert past.status_code == 400
        assert fake.calls == []
        assert client.get(f"/api/cv/suggestions?document_id={doc['id']}").json() == []


def test_ranges_count_utf16_like_the_editor(fake):
    fake.reply = '{"replace": "Mentored 30 students", "rationale": "Stronger verb."}'
    text = "# 🎓 Jane 😀\n\n- Taught 30 students\n"
    with TestClient(app) as client:
        doc = _doc(client, text)
        start = text.index("Taught")
        r = _ask(client, doc, text, start, start + len("Taught 30 students"))
        assert r.status_code == 200, r.text
        assert r.json()[0]["find"] == "Taught 30 students"


def test_a_version_is_suggested_against_and_tailoring_needs_a_target(fake):
    with TestClient(app) as client:
        doc = _doc(client)
        start = CV.index("Built")
        assert _ask(client, doc, CV, start, start + 5, action="tailor").status_code == 400

        v = client.post(f"/api/cv/documents/{doc['id']}/versions", json={"name": "For Lab X"}).json()

        async def label():
            async with SessionLocal() as session:
                await session.execute(
                    update(cv_models.CvTailoredVersion)
                    .where(cv_models.CvTailoredVersion.id == v["id"])
                    .values(target_label="Soft Robotics Lab, MIT")
                )
                await session.commit()

        asyncio.run(label())
        r = _ask(
            client, {**doc, "revision": v["revision"]}, CV, start, start + 5, action="tailor", version_id=v["id"]
        )
        assert r.status_code == 200, r.text
        assert r.json()[0]["version_id"] == v["id"]
        prompt = fake.calls[-1]["messages"][0]["content"]
        assert "Target: Soft Robotics Lab, MIT" in prompt and "speak to the target" in prompt

        other = _doc(client)
        wrong = _ask(client, {**other, "revision": v["revision"]}, CV, start, start + 5, version_id=v["id"])
        assert wrong.status_code == 400


def test_own_words_and_the_model_pick_are_passed_on(fake):
    with TestClient(app) as client:
        doc = _doc(client)
        start = CV.index("Built")
        empty = _ask(client, doc, CV, start, start + 5, action="custom")
        assert empty.status_code == 400

        r = _ask(
            client, doc, CV, start, start + 5, action="custom", instruction="Say crafted", model={"provider": "system"}
        )
        assert r.status_code == 200, r.text
        assert "Request: Say crafted" in fake.calls[-1]["messages"][0]["content"]
        # "system" is the shared model: no registry overrides.
        assert fake.kwargs[-1] == {}

        unknown = _ask(client, doc, CV, start, start + 5, model={"provider": "nope"})
        assert unknown.status_code == 400


def test_a_failed_or_empty_answer_stores_nothing(fake):
    with TestClient(app) as client:
        doc = _doc(client)
        start = CV.index("Built")
        fake.boom = True
        failed = _ask(client, doc, CV, start, start + 5)
        assert failed.status_code == 422
        fake.boom = False
        fake.reply = '{"replace": "Built", "rationale": "Fine as is."}'
        same = _ask(client, doc, CV, start, start + 5)
        assert same.status_code == 422
        assert client.get(f"/api/cv/suggestions?document_id={doc['id']}").json() == []


@pytest.mark.real_auth
def test_the_token_allowance_gates_suggestions(fake, monkeypatch):
    monkeypatch.setattr(settings, "billing_enforced", True)
    with TestClient(app) as client:
        email = f"suggest-{uuid.uuid4().hex[:8]}@example.com"
        reg = client.post(
            "/api/auth/register", json={"accept_terms": True, "email": email, "password": "long-enough-1"}
        ).json()
        user_id = reg["user"]["id"]
        h = {"Authorization": f"Bearer {reg['tokens']['access_token']}"}

        async def free():
            async with SessionLocal() as session:
                await session.execute(
                    update(auth_models.User).where(auth_models.User.id == user_id).values(plan="free")
                )
                await session.commit()

        asyncio.run(free())
        doc = _doc(client, headers=h)
        start = CV.index("Built")
        assert _ask(client, doc, CV, start, start + 5, headers=h).status_code == 200
        asyncio.run(metering.record(user_id, "chat", "p", "m", 2_000_000, 0))
        r = _ask(client, doc, CV, start, start + 5, headers=h)
        assert r.status_code == 402 and r.json()["detail"]["key"] == "model_tokens_per_month"
        assert len(fake.calls) == 1


def test_helpers():
    assert suggest.utf16_to_index("a😀b", 3) == 2
    assert suggest.utf16_to_index("a😀b", 2) is None  # inside the emoji
    assert suggest.utf16_to_index("ab", 3) is None
    text = "x\n- a\n- a\n- b\n"
    second = text.index("a", text.index("a") + 1)
    s, e = suggest.unique_span(text, second, second + 1)
    assert text[s:e].count("a") == 2 and text.count(text[s:e]) == 1  # widened to "- a\n- b"
    assert suggest.parse_reply('Sure: {"replace": "X", "rationale": "Y"}') == ("X", "Y")
    assert suggest.parse_reply("```\nPlain\n```") == ("Plain", None)
    assert suggest._same_edges(" a\n", "b") == " b\n"
