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
    ForbiddenError,
    NotFoundError,
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


async def _issue_pair(
    session, user: auth_models.User, audience: str = "app", *, commit: bool = True
) -> dict:
    check_account(user, audience)
    access = auth_security.issue_access_token(user.id, audience)
    raw, digest, expiry = auth_security.new_refresh_token(audience)
    session.add(
        auth_models.RefreshToken(
            user_id=user.id, token_hash=digest, expires_at=expiry, audience=audience
        )
    )
    if commit:
        await session.commit()
    return {"access_token": access, "refresh_token": raw, "token_type": "bearer"}


async def register(
    session,
    email: str,
    password: str,
    accept_terms: bool = False,
    track: str | None = None,
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
    if track:
        from api.opportunities import service as opportunities

        try:
            opportunity = await opportunities.get_or_404(session, track)
        except NotFoundError:
            pass
        else:
            await opportunities.track(session, user.id, opportunity.id)
    tokens = await _issue_pair(session, user)
    return {"user": to_user_out(user), "tokens": tokens}


async def login(
    session, email: str, password: str, audience: str = "app", *, commit: bool = True
) -> dict:
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
    check_account(user, audience)
    auth_security.clear_login_failures(address)
    tokens = await _issue_pair(session, user, audience, commit=commit)
    return {"user": to_user_out(user), "tokens": tokens}


async def refresh(
    session, refresh_token: str, audience: str = "app", *, commit: bool = True
) -> dict:
    digest = auth_security.hash_token(refresh_token)
    grant = (
        await session.execute(
            select(auth_models.RefreshToken)
            .where(
                auth_models.RefreshToken.token_hash == digest,
                auth_models.RefreshToken.audience == audience,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if grant is None:
        raise AuthError("Refresh token is unknown or already used.")
    if grant.expires_at <= utcnow_naive():
        raise AuthError("Refresh token expired; sign in again.")
    user = await session.get(auth_models.User, grant.user_id)
    if user is None:
        raise AuthError("Account is gone; sign in again.")
    check_account(user, audience)
    await session.delete(grant)
    tokens = await _issue_pair(session, user, audience, commit=commit)
    return {"user": to_user_out(user), "tokens": tokens}


async def logout(
    session,
    refresh_token: str,
    push_endpoint: str | None = None,
    audience: str = "app",
    *,
    commit: bool = True,
) -> dict:
    digest = auth_security.hash_token(refresh_token)
    revoked = (
        await session.execute(
            delete(auth_models.RefreshToken)
            .where(
                auth_models.RefreshToken.token_hash == digest,
                auth_models.RefreshToken.audience == audience,
            )
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
    if commit:
        await session.commit()
    return {"status": "signed out"}


async def get_user_or_401(session, user_id: str) -> auth_models.User:
    user = await session.get(auth_models.User, user_id)
    if user is None:
        raise AuthError("Account is gone; sign in again.")
    check_account(user)
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
    if user.role == "admin":
        from sqlalchemy import func

        await session.execute(
            select(func.pg_advisory_xact_lock(func.hashtext("staff-roles")))
        )
        others = await session.scalar(
            select(func.count())
            .select_from(auth_models.User)
            .where(
                auth_models.User.role == "admin",
                auth_models.User.disabled_at.is_(None),
                auth_models.User.id != user.id,
            )
        )
        if not others:
            raise BadRequestError("The last active admin cannot delete their account.")
    if user.password_hash.startswith("!"):
        # Sign-in-provider accounts have no password: confirm with the email.
        if password.strip().lower() != user.email:
            raise AuthError("Type your account email exactly to confirm.")
    elif not auth_security.check_password(password, user.password_hash):
        raise AuthError("Password is incorrect.")
    from api.applicant_kit.service import lock_member
    from api.applicant_kit.storage import get_storage

    await lock_member(session, user_id)
    await get_storage().delete_member(user_id)
    await session.execute(
        delete(auth_models.RefreshToken).where(
            auth_models.RefreshToken.user_id == user.id
        )
    )
    await session.delete(user)
    await session.commit()
    return {"status": "account deleted"}


def check_account(user, audience="app"):
    if user.disabled_at is not None:
        raise ForbiddenError("Account is disabled.")
    if audience == "admin" and (
        user.role not in ("editor", "admin") or user.email_verified_at is None
    ):
        raise ForbiddenError("Verified staff access required.")


async def seed_admins(session):
    addresses = {
        e.strip().lower() for e in settings.ops_admin_emails.split(",") if e.strip()
    }
    if addresses:
        from sqlalchemy import update

        await session.execute(
            update(auth_models.User)
            .where(
                auth_models.User.email.in_(addresses),
                auth_models.User.role == "member",
                auth_models.User.email_verified_at.is_not(None),
            )
            .values(role="admin")
        )
        await session.commit()
