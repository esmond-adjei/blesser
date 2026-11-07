"""Profile basics: display name and avatar.

Avatars are validated like CV uploads, then always re-encoded to a 256px WebP,
which strips EXIF (including GPS) and anything smuggled after the image data.
"""

import io
import secrets
import unicodedata

from PIL import Image, UnidentifiedImageError

from api.auth import models as auth_models
from api.core.exceptions import BadRequestError

MAX_AVATAR_BYTES = 5 * 1024 * 1024
MAX_SOURCE_PIXELS = 25_000_000  # ~5000x5000; larger is a decompression bomb risk
AVATAR_SIZE = 256
NAME_MAX = 80

_MAGIC = {
    b"\x89PNG\r\n\x1a\n": "png",
    b"\xff\xd8\xff": "jpeg",
}


def _sniff(data: bytes) -> str | None:
    for magic, kind in _MAGIC.items():
        if data.startswith(magic):
            return kind
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def normalize_name(raw: str | None) -> str | None:
    """Trim, collapse whitespace, drop control characters; '' clears."""
    if raw is None:
        return None
    cleaned = "".join(ch for ch in raw if unicodedata.category(ch)[0] != "C")
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return None
    if len(cleaned) > NAME_MAX:
        raise BadRequestError(f"Name is too long (max {NAME_MAX} characters).")
    return cleaned


def process_avatar(data: bytes) -> bytes:
    """Validate an upload and return the re-encoded 256px WebP."""
    if not data:
        raise BadRequestError("The file is empty.")
    if len(data) > MAX_AVATAR_BYTES:
        raise BadRequestError("Pictures must be 5 MB or smaller.")
    if _sniff(data) is None:
        raise BadRequestError("Use a PNG, JPEG or WebP image.")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            width, height = probe.size
            if width * height > MAX_SOURCE_PIXELS:
                raise BadRequestError(
                    "That image is too large. Use one under 5000 by 5000 pixels."
                )
            probe.verify()
        with Image.open(io.BytesIO(data)) as img:
            img = img.convert("RGB")
            side = min(img.size)
            left = (img.width - side) // 2
            top = (img.height - side) // 2
            img = img.crop((left, top, left + side, top + side))
            img = img.resize((AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            img.save(out, format="WEBP", quality=85, method=6)
            return out.getvalue()
    except BadRequestError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
    ) as exc:
        raise BadRequestError("That file isn't a readable image.") from exc


async def update_profile(
    session, user: auth_models.User, display_name: str | None
) -> None:
    user.display_name = normalize_name(display_name)
    await session.commit()


async def set_avatar(session, user: auth_models.User, data: bytes) -> None:
    user.avatar = process_avatar(data)
    # New key per upload: old URLs stop resolving, caches stay immutable.
    user.avatar_key = secrets.token_urlsafe(24)
    await session.commit()


async def clear_avatar(session, user: auth_models.User) -> None:
    user.avatar = None
    user.avatar_key = None
    await session.commit()
