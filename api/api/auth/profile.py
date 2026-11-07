"""Profile basics: the display name."""

import unicodedata

from api.auth import models as auth_models
from api.core.exceptions import BadRequestError

NAME_MAX = 80


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


async def update_profile(session, user: auth_models.User, display_name: str | None) -> None:
    user.display_name = normalize_name(display_name)
    await session.commit()
