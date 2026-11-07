import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from api.agent.llm.base import LLMResponse
from api.core.db import SessionLocal
from api.cv import models as cv_models
from api.main import app
from api.runs import interests
from tests.cv_fixtures import DocxBuilder, heading, para


@pytest.fixture
def storage_dir(tmp_path, monkeypatch):
    from api.core.config import settings

    monkeypatch.setattr(settings, "cv_storage_dir", str(tmp_path / "cv_storage"))
    return tmp_path


@pytest.fixture(autouse=True)
def _clean(storage_dir):
    async def _wipe():
        async with SessionLocal() as session:
            for m in (
                cv_models.CvSuggestion,
                cv_models.CvTailoredVersion,
                cv_models.CvDocument,
            ):
                await session.execute(delete(m))
            await session.commit()

    asyncio.run(_wipe())
    yield
    asyncio.run(_wipe())


def _cv(research: str = "Learning-based control for legged robots; sim-to-real transfer.") -> bytes:
    b = DocxBuilder()
    b.body = [
        heading("Jane Doe"),
        heading("Research"),
        para(research),
        para("Model predictive control for agile quadruped locomotion.", bullet=True),
        heading("Experience"),
        para("Barista at a coffee shop, 2019-2020.", bullet=True),
    ]
    return b.build()


def _upload(client, title="Main CV", **cv):
    resp = client.post(
        "/api/cv/documents",
        files={
            "file": (
                "cv.docx",
                _cv(**cv),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={"title": title},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class _Fake:
    def __init__(self, text=None, boom=False):
        self.text, self.boom = text, boom

    async def chat(self, messages, system, tools, max_tokens=4096):
        if self.boom:
            raise RuntimeError("no key")
        # Cite the first excerpt id we were sent, plus one made-up id.
        first = messages[0]["content"].split("]")[0].lstrip("[")
        return LLMResponse(
            text=f'{{"interests": [{{"text": "Learning-based legged locomotion", "unit": "{first}"}},'
            ' {"text": "Underwater basket weaving", "unit": "invented"}]}',
            tool_calls=[],
        )


def test_no_documents_is_an_empty_unchanged_flow():
    with TestClient(app) as client:
        body = client.post("/api/runs/interest-suggestions").json()
        assert body == {"sources": [], "suggestions": [], "method": "none"}


def test_model_suggestions_cite_real_units_only(monkeypatch):
    monkeypatch.setattr(interests, "get_provider", lambda **_: _Fake())
    with TestClient(app) as client:
        doc = _upload(client)
        body = client.post("/api/runs/interest-suggestions").json()
    assert body["method"] == "model"
    texts = [s["text"] for s in body["suggestions"]]
    assert texts == ["Learning-based legged locomotion"]  # uncited phrase dropped
    s = body["suggestions"][0]
    assert s["document_id"] == doc["id"] and s["document_title"] == "Main CV"
    assert s["section"] == "research" and "legged robots" in s["evidence"]


def test_falls_back_to_heuristic_without_a_model(monkeypatch):
    monkeypatch.setattr(interests, "get_provider", lambda **_: _Fake(boom=True))
    with TestClient(app) as client:
        _upload(client)
        body = client.post("/api/runs/interest-suggestions").json()
    assert body["method"] == "heuristic"
    texts = " | ".join(s["text"] for s in body["suggestions"])
    assert "legged robots" in texts
    assert "Barista" not in texts  # experience section is not interest-bearing


def test_reads_only_the_chosen_cv(monkeypatch):
    monkeypatch.setattr(interests, "get_provider", lambda **_: _Fake(boom=True))
    with TestClient(app) as client:
        _upload(client)
        other = _upload(client, title="Ocean CV", research="Coral reef acoustics; passive sonar monitoring.")
        body = client.post("/api/runs/interest-suggestions", json={"document_id": other["id"]}).json()
        everything = client.post("/api/runs/interest-suggestions").json()
    assert body["sources"] == [{"document_id": other["id"], "title": "Ocean CV"}]
    texts = " | ".join(s["text"] for s in body["suggestions"])
    assert "Coral reef acoustics" in texts and "legged" not in texts
    # No choice: the newest few.
    assert {s["title"] for s in everything["sources"]} == {"Main CV", "Ocean CV"}


def test_unknown_cv_is_not_found():
    with TestClient(app) as client:
        r = client.post("/api/runs/interest-suggestions", json={"document_id": "nope"})
    assert r.status_code == 404
