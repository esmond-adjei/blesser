"""Bounded chat uploads; documents go through the extraction sandbox.

Every turn resends the history, so only the newest image turns keep their
bytes; older ones become a note naming the image."""

import base64
import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from api.core.exceptions import BadRequestError
from api.cv.service import markdown_from_upload, upload_format

MAX_BYTES = 2 * 1024 * 1024
THUMB_PX = 160
#: User turns, newest first, whose images are still sent to the model.
KEEP_IMAGE_TURNS = 2


def _thumbnail(data: bytes) -> str:
    """A small JPEG of the image for the chat bubble, as a data URL."""
    with Image.open(io.BytesIO(data)) as image:
        image.thumbnail((THUMB_PX, THUMB_PX))
        buf = io.BytesIO()
        image.convert("RGB").save(buf, "JPEG", quality=70)
    return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"


async def read_attachment(filename: str, data: bytes) -> dict:
    name = Path(filename).name[:200] or "Attachment"
    if not data or len(data) > MAX_BYTES:
        raise BadRequestError("Attach a non-empty file up to 2 MB.")
    if Path(name).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        try:
            with Image.open(io.BytesIO(data)) as image:
                mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}.get(image.format)
                if not mime or image.width * image.height > 16_000_000:
                    raise BadRequestError("Use a PNG, JPEG or WebP image up to 16 megapixels.")
                image.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise BadRequestError("Couldn't read that image.") from exc
        return {
            "kind": "image",
            "name": name,
            "data_url": f"data:{mime};base64,{base64.b64encode(data).decode()}",
            "thumb_url": _thumbnail(data),
        }
    fmt = upload_format(name)
    try:
        text = await markdown_from_upload(fmt, name, data)
    except BadRequestError as exc:
        # The CV wording ("upload the DOCX") doesn't fit a chat attachment.
        if "no text" not in str(exc).lower():
            raise
        hint = " If it's a scan, attach the pages as images instead." if fmt == "pdf" else ""
        raise BadRequestError(f"No text could be read from {name}.{hint}") from exc
    if len(text) > 20000:
        raise BadRequestError(f"{name} has more than 20,000 characters of text. Attach a shorter document or an excerpt.")
    return {"kind": "text", "name": name, "text": text}


def summary(attachments: list[dict]) -> list[dict]:
    """What the chat bubble shows for each attachment: no document text,
    no full-size image."""
    out = []
    for item in attachments:
        row = {"kind": item["kind"], "name": item["name"]}
        if item["kind"] == "image" and item.get("thumb_url"):
            row["thumb_url"] = item["thumb_url"]
        if item["kind"] == "text":
            row["chars"] = len(item.get("text") or "")
        out.append(row)
    return out


def prune_images(history: list[dict], keep: int = KEEP_IMAGE_TURNS) -> None:
    """Drop the image bytes of all but the newest `keep` user turns that
    carry images, in place. The name stays, so the model knows one was shared."""
    seen = 0
    for message in reversed(history):
        if message.get("role") != "user":
            continue
        images = [a for a in message.get("attachments") or [] if a.get("kind") == "image" and a.get("data_url")]
        if not images:
            continue
        seen += 1
        if seen <= keep:
            continue
        for item in images:
            item.pop("data_url", None)
            item.pop("thumb_url", None)
            item["pruned"] = True


def user_blocks(message: dict, provider: str) -> list[dict]:
    blocks = [{"type": "text", "text": str(message.get("content", ""))}]
    for item in message.get("attachments") or []:
        if item["kind"] == "text":
            blocks.append({"type": "text", "text": f"[Attached document: {item['name']}]\n{item['text']}"})
        elif not item.get("data_url"):
            blocks.append({"type": "text", "text": (
                f"[Image {item['name']} was attached earlier and is no longer sent. "
                "Ask the student to attach it again if you need to look at it.]"
            )})
        elif provider == "anthropic":
            prefix, encoded = item["data_url"].split(",", 1)
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": prefix[5:].split(";")[0], "data": encoded}})
        else:
            blocks.append({"type": "image_url", "image_url": {"url": item["data_url"]}})
    return blocks
