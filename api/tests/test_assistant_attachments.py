import asyncio
import io

import pytest
from docx import Document
from PIL import Image
from reportlab.pdfgen import canvas

from api.assistant.attachments import prune_images, read_attachment, user_blocks
from api.core.exceptions import BadRequestError


def test_document_uploads_reach_the_model_as_extracted_text():
    pdf = io.BytesIO()
    page = canvas.Canvas(pdf)
    page.drawString(72, 720, "Research on soft robotics")
    page.save()

    word = io.BytesIO()
    document = Document()
    document.add_paragraph("Research on soft robotics")
    document.save(word)

    for name, data in [
        ("paper.pdf", pdf.getvalue()),
        ("notes.docx", word.getvalue()),
        ("notes.txt", b"Research on soft robotics"),
    ]:
        attachment = asyncio.run(read_attachment(name, data))
        blocks = user_blocks(
            {"content": "Summarize this", "attachments": [attachment]}, "openai"
        )
        assert attachment["kind"] == "text"
        assert "Research on soft robotics" in blocks[1]["text"]


def test_image_upload_reaches_supported_provider_message_shapes():
    image = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(image, format="PNG")
    attachment = asyncio.run(read_attachment("figure.png", image.getvalue()))
    message = {"content": "Describe this figure", "attachments": [attachment]}
    assert user_blocks(message, "openai")[1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )
    anthropic = user_blocks(message, "anthropic")[1]
    assert anthropic["type"] == "image"
    assert anthropic["source"]["media_type"] == "image/png"


def _png(size=(400, 300)) -> bytes:
    image = io.BytesIO()
    Image.new("RGB", size, "red").save(image, format="PNG")
    return image.getvalue()


def test_image_uploads_carry_a_small_thumbnail():
    attachment = asyncio.run(read_attachment("figure.png", _png()))
    assert attachment["thumb_url"].startswith("data:image/jpeg;base64,")
    assert len(attachment["thumb_url"]) < len(attachment["data_url"])


def test_a_pdf_without_text_says_so_and_suggests_images():
    pdf = io.BytesIO()
    page = canvas.Canvas(pdf)
    page.rect(72, 72, 100, 100)  # a drawing, no text: like a scan
    page.save()
    with pytest.raises(BadRequestError, match=r"No text could be read from scan\.pdf\. If it's a scan"):
        asyncio.run(read_attachment("scan.pdf", pdf.getvalue()))


def test_only_the_latest_image_turns_keep_their_bytes():
    def turn(name):
        return {"role": "user", "content": name, "attachments": [{"kind": "image", "name": name, "data_url": "data:image/png;base64,AAAA"}]}

    history = [turn("one.png"), {"role": "assistant", "content": "ok"}, turn("two.png"), turn("three.png")]
    prune_images(history)
    assert [bool(m["attachments"][0].get("data_url")) for m in history if m["role"] == "user"] == [False, True, True]
    note = user_blocks(history[0], "openai")[1]["text"]
    assert "one.png" in note and "no longer sent" in note


def test_a_turns_attachments_show_on_its_message(monkeypatch):
    import api.assistant.service as gradis
    from tests.test_assistant import ScriptProvider, _client, _transcript, _turn

    provider = ScriptProvider([(["A red square."], [])])
    monkeypatch.setattr(gradis, "get_provider", lambda: provider)
    image = asyncio.run(read_attachment("figure.png", _png()))
    note = {"kind": "text", "name": "notes.txt", "text": "Robotics"}
    with _client() as client:
        conv_id = client.post("/api/assistant/conversations").json()["id"]
        _turn(client, conv_id, "What is this?", context={"attachments": [image, note]})
        user = next(m for m in _transcript(client, conv_id) if m["role"] == "user")

    assert user["content"] == "What is this?"
    assert user["attachments"] == [
        {"kind": "image", "name": "figure.png", "thumb_url": image["thumb_url"]},
        {"kind": "text", "name": "notes.txt", "chars": 8},
    ]
    sent = next(m for m in provider.seen[0] if m.get("role") == "user")
    assert sent["attachments"][0]["data_url"] == image["data_url"]
    assert "thumb_url" not in sent["attachments"][0]
