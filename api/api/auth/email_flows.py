"""Password reset and email verification over single-use emailed links.

Reset answers identically whether or not the account exists, is throttled per
email and per IP, and on use burns other reset links, revokes all sessions and
clears the login lockout. Unverified accounts work; sensitive actions call
`require_verified`. Tokens are stored only as SHA-256 hashes.
"""

import secrets
from datetime import timedelta
from urllib.parse import quote

from sqlalchemy import delete, select, update

from api.auth import models as auth_models
from api.auth import security as auth_security
from api.core import mailer
from api.core.config import settings
from api.core.exceptions import BadRequestError, ForbiddenError, RateLimitError
from api.core.mail_layout import compose
from api.core.time import utcnow_naive

RESET = "reset"
VERIFY = "verify"


def _link(path: str, token: str) -> str:
    return f"{settings.app_base_url.rstrip('/')}{path}?token={quote(token)}"


async def _issue(session, user_id: str, purpose: str, ttl: timedelta) -> str:
    raw = secrets.token_urlsafe(32)
    session.add(
        auth_models.EmailToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=auth_security.hash_token(raw),
            expires_at=utcnow_naive() + ttl,
        )
    )
    await session.commit()
    return raw


async def _consume(session, raw: str, purpose: str) -> auth_models.EmailToken:
    row = (
        await session.execute(
            select(auth_models.EmailToken).where(
                auth_models.EmailToken.token_hash == auth_security.hash_token(raw or ""),
                auth_models.EmailToken.purpose == purpose,
            )
        )
    ).scalar_one_or_none()
    if row is None or row.used_at is not None or row.expires_at <= utcnow_naive():
        noun = "reset" if purpose == RESET else "verification"
        raise BadRequestError(
            f"This {noun} link is invalid or has expired. Request a new one."
        )
    row.used_at = utcnow_naive()
    return row


async def request_password_reset(session, email: str) -> mailer.Mail | None:
    """Return the mail to send (caller sends in the background), or None
    when no such account exists. Callers answer identically either way."""
    address = email.strip().lower()
    user = (
        await session.execute(
            select(auth_models.User).where(auth_models.User.email == address)
        )
    ).scalar_one_or_none()
    if user is None:
        return None
    raw = await _issue(
        session, user.id, RESET, timedelta(minutes=settings.password_reset_minutes)
    )
    link = _link("/reset-password", raw)
    return compose(
        to=user.email,
        subject="Reset your Blesser password",
        heading="Reset your password",
        paragraphs=["Someone (hopefully you) asked to reset the password for this Blesser account."],
        action=("Choose a new password", link),
        note=(
            f"The link works once and expires in {settings.password_reset_minutes} minutes. "
            "If you didn't ask for this, ignore this email; your password stays the same."
        ),
    )


async def reset_password(session, raw_token: str, new_password: str) -> None:
    token = await _consume(session, raw_token, RESET)
    user = await session.get(auth_models.User, token.user_id)
    if user is None:  # pragma: no cover - cascade removes tokens with users
        raise BadRequestError(
            "This reset link is invalid or has expired. Request a new one."
        )
    user.password_hash = auth_security.hash_password(new_password)
    # A mailbox that can reset can also verify: the address is proven.
    user.email_verified_at = user.email_verified_at or utcnow_naive()
    # Burn other outstanding reset links and every session.
    await session.execute(
        update(auth_models.EmailToken)
        .where(
            auth_models.EmailToken.user_id == user.id,
            auth_models.EmailToken.purpose == RESET,
            auth_models.EmailToken.used_at.is_(None),
        )
        .values(used_at=utcnow_naive())
    )
    await session.execute(
        delete(auth_models.RefreshToken).where(
            auth_models.RefreshToken.user_id == user.id
        )
    )
    await session.commit()
    auth_security.clear_login_failures(user.email)


async def verification_mail(session, user: auth_models.User) -> mailer.Mail:
    raw = await _issue(
        session, user.id, VERIFY, timedelta(hours=settings.email_verify_hours)
    )
    return compose(
        to=user.email,
        subject="Confirm your email for Blesser",
        heading="Confirm your email",
        paragraphs=["Confirm this address to unlock account features like data export and email notifications."],
        action=("Confirm email", _link("/verify-email", raw)),
        note=f"The link expires in {settings.email_verify_hours} hours. If you didn't create a Blesser account, ignore this email.",
    )


async def resend_verification(session, user: auth_models.User) -> mailer.Mail:
    if user.email_verified_at is not None:
        raise BadRequestError("Your email is already confirmed.")
    last = (
        await session.execute(
            select(auth_models.EmailToken.created_at)
            .where(
                auth_models.EmailToken.user_id == user.id,
                auth_models.EmailToken.purpose == VERIFY,
            )
            .order_by(auth_models.EmailToken.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    cooldown = settings.email_verify_resend_seconds
    if last is not None:
        waited = (utcnow_naive() - last).total_seconds()
        if waited < cooldown:
            wait = int(cooldown - waited) + 1
            raise RateLimitError(
                f"We just sent one. Try again in {wait} seconds.", retry_after=wait
            )
    return await verification_mail(session, user)


async def verify_email(session, raw_token: str) -> auth_models.User:
    token = await _consume(session, raw_token, VERIFY)
    user = await session.get(auth_models.User, token.user_id)
    if user is None:  # pragma: no cover
        raise BadRequestError(
            "This verification link is invalid or has expired. Request a new one."
        )
    user.email_verified_at = user.email_verified_at or utcnow_naive()
    await session.commit()
    return user


def require_verified(user: auth_models.User) -> None:
    """Gate for sensitive actions (data export, account linking)."""
    if user.email_verified_at is None:
        raise ForbiddenError(
            "Confirm your email address first. We can resend the link."
        )
