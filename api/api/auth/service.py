"""Auth storage: registration, credential checks, refresh rotation (hashes only)."""

from datetime import UTC, datetime

from sqlalchemy import delete, select

from api.auth import models as auth_models
from api.auth import security as auth_security
from api.core.config import settings
from api.core.exceptions import (
    AuthError,
    BadRequestError,
    ConflictError,
    RateLimitError,
)
from api.core.time import utcnow_naive


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def to_user_out(user: auth_models.User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "created_at": user.created_at,
        "display_name": user.display_name,
        "email_verified": user.email_verified_at is not None,
        "has_password": not user.password_hash.startswith("!"),
    }


async def issue_pair(session, user: auth_models.User) -> dict:
    """Session for other sign-in methods: access token + rotating refresh grant."""
    return await _issue_pair(session, user)


async def _issue_pair(session, user: auth_models.User) -> dict:
    access = auth_security.issue_access_token(user.id)
    raw, digest, expiry = auth_security.new_refresh_token()
    session.add(
        auth_models.RefreshToken(user_id=user.id, token_hash=digest, expires_at=expiry)
    )
    await session.commit()
    return {"access_token": access, "refresh_token": raw, "token_type": "bearer"}


async def register(
    session, email: str, password: str, accept_terms: bool = False
) -> dict:
    if not accept_terms:
        raise BadRequestError(
            "Agree to the Terms and the Privacy notice to create an account."
        )
    address = _normalize_email(email)
    existing = (
        await session.execute(
            select(auth_models.User).where(auth_models.User.email == address)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("An account with that email already exists.")
    user = auth_models.User(
        email=address,
        password_hash=auth_security.hash_password(password),
        terms_accepted_at=datetime.now(UTC).replace(tzinfo=None),
        terms_version=settings.terms_version,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    tokens = await _issue_pair(session, user)
    return {"user": to_user_out(user), "tokens": tokens}


async def login(session, email: str, password: str) -> dict:
    address = _normalize_email(email)
    if not auth_security.login_allowed(address):
        raise RateLimitError("Too many failed attempts; try again in a minute.")
    user = (
        await session.execute(
            select(auth_models.User).where(auth_models.User.email == address)
        )
    ).scalar_one_or_none()
    if user is None or not auth_security.check_password(password, user.password_hash):
        auth_security.record_login_failure(address)
        raise AuthError("Wrong email or password.")
    auth_security.clear_login_failures(address)
    tokens = await _issue_pair(session, user)
    return {"user": to_user_out(user), "tokens": tokens}


async def refresh(session, refresh_token: str) -> dict:
    digest = auth_security.hash_token(refresh_token)
    grant = (
        await session.execute(
            select(auth_models.RefreshToken).where(
                auth_models.RefreshToken.token_hash == digest
            )
        )
    ).scalar_one_or_none()
    if grant is None:
        raise AuthError("Refresh token is unknown or already used.")
    if grant.expires_at <= utcnow_naive():
        await session.delete(grant)
        await session.commit()
        raise AuthError("Refresh token expired; sign in again.")
    user = await session.get(auth_models.User, grant.user_id)
    if user is None:
        await session.delete(grant)
        await session.commit()
        raise AuthError("Account is gone; sign in again.")
    # Rotation: the presented grant dies here, so a replay shows up as unknown.
    await session.delete(grant)
    await session.commit()
    tokens = await _issue_pair(session, user)
    return {"user": to_user_out(user), "tokens": tokens}


async def logout(session, refresh_token: str, push_endpoint: str | None = None) -> dict:
    digest = auth_security.hash_token(refresh_token)
    revoked = (
        await session.execute(
            delete(auth_models.RefreshToken)
            .where(auth_models.RefreshToken.token_hash == digest)
            .returning(auth_models.RefreshToken.user_id)
        )
    ).scalar_one_or_none()
    if revoked is not None and push_endpoint:
        # Only this grant's account's subscription: the endpoint alone proves nothing.
        from api.notifications import models as notification_models

        await session.execute(
            delete(notification_models.PushSubscription).where(
                notification_models.PushSubscription.user_id == revoked,
                notification_models.PushSubscription.endpoint == push_endpoint,
            )
        )
    await session.commit()
    return {"status": "signed out"}


async def get_user_or_401(session, user_id: str) -> auth_models.User:
    user = await session.get(auth_models.User, user_id)
    if user is None:
        raise AuthError("Account is gone; sign in again.")
    return user


async def change_password(
    session, user_id: str, current_password: str, new_password: str
) -> dict:
    """Change password after proving the current one; other sessions stay signed in."""
    user = await get_user_or_401(session, user_id)
    if not auth_security.check_password(current_password, user.password_hash):
        raise AuthError("Current password is incorrect.")
    user.password_hash = auth_security.hash_password(new_password)
    await session.commit()
    return {"status": "password updated"}


async def delete_account(session, user_id: str, password: str) -> dict:
    """Delete the user row; everything it owns cascades."""
    user = await get_user_or_401(session, user_id)
    if user.password_hash.startswith("!"):
        # Sign-in-provider accounts have no password: confirm with the email.
        if password.strip().lower() != user.email:
            raise AuthError("Type your account email exactly to confirm.")
    elif not auth_security.check_password(password, user.password_hash):
        raise AuthError("Password is incorrect.")
    await session.execute(
        delete(auth_models.RefreshToken).where(
            auth_models.RefreshToken.user_id == user.id
        )
    )
    await session.delete(user)
    await session.commit()
    return {"status": "account deleted"}
