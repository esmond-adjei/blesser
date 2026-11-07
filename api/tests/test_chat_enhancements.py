import asyncio
import io
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api.agent.llm.openai_compat_provider import OpenAICompatProvider
from api.agent.tool_preview import preview
from api.assistant.attachments import user_blocks
from api.billing.service import estimate_tokens
from api.core.db import SessionLocal
from api.core.exceptions import NotFoundError
from api.cv import docx_export, pdf_export
from api.main import app
from api.prospects.models import ProfessorIndex
from tests.conftest import TEST_USER_ID


def test_index_only_professor_has_an_owned_detail_and_search_hit():
    tag = uuid4().hex

    async def seed():
        async with SessionLocal() as session:
            entry = ProfessorIndex(user_id=TEST_USER_ID, name=f"Ada {tag}", name_key=tag,
                                   school_name="Index University", school_key=tag,
                                   openalex_id="A123", author={}, outcome="no_match",
                                   works=[{"title": "Robotics", "year": 2025}],
                                   looked_up_at=datetime.now(UTC).replace(tzinfo=None))
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            return entry.id

    id_ = asyncio.run(seed())

    async def other_account():
        from api.assistant.search import search_everything
        from api.prospects.service import get_professor
        async with SessionLocal() as session:
            with pytest.raises(NotFoundError):
                await get_professor(session, "another-account", id_)
            assert (await search_everything(session, "another-account", tag))["total"] == 0
    asyncio.run(other_account())
    with TestClient(app) as client:
        result = client.get(f"/api/professors/{id_}")
        assert result.status_code == 200
        assert result.json()["name"] == f"Ada {tag}"
        assert result.json()["papers"] == [{"id": None, "title": "Robotics", "year": 2025, "abstract": None, "url": None, "citations": None, "publication_type": None, "coauthors": []}]
        hits = client.get("/api/search", params={"q": tag}).json()["items"]
        assert any(h["id"] == id_ and h["href"] == f"/professors/{id_}" for h in hits)
        assert client.get("/api/professors/missing").status_code == 404


def test_search_finds_saved_papers_and_any_document_kind():
    tag = uuid4().hex

    async def seed():
        from api.cv.models import CvDocument
        from api.prospects.models import Paper, Professor, Program, School
        async with SessionLocal() as session:
            school = School(user_id=TEST_USER_ID, name="Paper University")
            session.add(school)
            await session.flush()
            program = Program(user_id=TEST_USER_ID, school_id=school.id, name="PhD")
            session.add(program)
            await session.flush()
            prof = Professor(user_id=TEST_USER_ID, program_id=program.id, name="Lin")
            session.add(prof)
            await session.flush()
            paper = Paper(user_id=TEST_USER_ID, professor_id=prof.id, title=f"Walking {tag}", year=2024)
            doc = CvDocument(user_id=TEST_USER_ID, title=f"SOP {tag}", kind="sop", markdown="")
            session.add_all([paper, doc])
            await session.commit()
            return prof.id, paper.id, doc.id

    prof_id, paper_id, doc_id = asyncio.run(seed())
    with TestClient(app) as client:
        hits = {h["kind"]: h for h in client.get("/api/search", params={"q": tag}).json()["items"]}
    assert hits["paper"]["id"] == paper_id
    assert hits["paper"]["href"] == f"/professors/{prof_id}?paper={paper_id}"
    assert hits["paper"]["subtitle"] == "Lin · 2024"
    assert hits["document"]["id"] == doc_id
    assert hits["document"]["subtitle"] == "Statement of purpose"


def test_model_info_uses_the_resolved_system_model():
    with TestClient(app) as client:
        response = client.get("/api/assistant/model-info", params={"provider": "system"})
        assert response.status_code == 200
        assert response.json()["model"]
        assert response.json()["input_tokens"] > 0
        assert client.get("/api/assistant/model-info", params={"conversation_id": "not-owned"}).status_code == 404


def test_attachments_are_read_without_creating_cv_documents():
    with TestClient(app) as client:
        text = client.post("/api/assistant/attachments", files={"file": ("notes.txt", b"Research interests: robotics", "text/plain")})
        assert text.status_code == 200
        assert text.json() == {"kind": "text", "name": "notes.txt", "text": "Research interests: robotics"}
        image = io.BytesIO()
        Image.new("RGB", (2, 2), "white").save(image, format="PNG")
        response = client.post("/api/assistant/attachments", files={"file": ("figure.png", image.getvalue(), "image/png")})
        assert response.status_code == 200
        item = response.json()
        assert item["data_url"].startswith("data:image/png;base64,")
        blocks = user_blocks({"content": "Explain", "attachments": [item]}, "anthropic")
        assert blocks[1]["source"]["media_type"] == "image/png"
        assert client.post("/api/assistant/attachments", files={"file": ("fake.png", b"not an image")}).status_code == 400
        assert client.post("/api/assistant/attachments", files={"file": ("large.txt", b"x" * (2 * 1024 * 1024 + 1))}).status_code == 400


def test_effort_is_forwarded_with_a_reasoning_model_output_budget():
    sent = []

    async def create(**kwargs):
        sent.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Answer", tool_calls=[]))])

    provider = OpenAICompatProvider(model="gpt-5", api_key="test", provider_label="openai")
    provider.effort = "high"
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    asyncio.run(provider.chat([{"role": "user", "content": "Explain"}], "", [], 2048))
    assert sent[0]["reasoning_effort"] == "high"
    assert sent[0]["max_completion_tokens"] == 2048
    assert "max_tokens" not in sent[0]


def test_large_tool_previews_stay_valid_and_keep_record_identity():
    result = json.loads(preview({"id": "record-1", "items": [{"body": "x" * 5000}] * 100}, 1000))
    assert result["id"] == "record-1"
    assert len(json.dumps(result)) <= 1000


def test_image_context_estimate_counts_image_tokens_instead_of_base64_bytes():
    small = [{"content": "Explain", "attachments": [{"kind": "image", "name": "x", "data_url": "x" * 10}]}]
    large = [{"content": "Explain", "attachments": [{"kind": "image", "name": "x", "data_url": "x" * 1_000_000}]}]
    assert estimate_tokens(small, "", 0) == estimate_tokens(large, "", 0)
    assert 4096 <= estimate_tokens(large, "", 0) < 4200


def test_exported_cv_text_and_links_are_black():
    assert pdf_export.INK.hexval() == "0x000000"
    assert 'color="#000000"' in pdf_export.inline("[Website](https://example.com)")
    assert str(docx_export.INK) == "000000"
    assert str(docx_export.LINK) == "000000"
