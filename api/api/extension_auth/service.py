from datetime import timedelta

from sqlalchemy import delete, select

from api.auth import security
from api.auth.models import RefreshToken, User
from api.auth.service import check_account, to_user_out
from api.core.exceptions import AuthError, NotFoundError
from api.core.ids import new_id
from api.core.time import utcnow_naive
from api.extension_auth.models import ExtensionSession


def session_out(browser):
    return {
        key: getattr(browser, key)
        for key in ("id", "name", "created_at", "last_used_at")
    }


def issue_pair(session, browser):
    raw, digest, expiry = security.new_refresh_token("ext")
    session.add(
        RefreshToken(
            user_id=browser.user_id,
            audience="ext",
            extension_session_id=browser.id,
            token_hash=digest,
            expires_at=expiry,
        )
    )
    return {
        "access_token": security.issue_access_token(
            browser.user_id, "ext", session_id=browser.id
        ),
        "refresh_token": raw,
    }


async def connect(session, user_id, name):
    browser = ExtensionSession(id=new_id(), user_id=user_id, name=name)
    session.add(browser)
    await session.flush()
    result = issue_pair(session, browser)
    await session.commit()
    return {**result, "session": session_out(browser)}


async def revoke(session, browser):
    browser.revoked_at = browser.revoked_at or utcnow_naive()
    await session.execute(
        delete(RefreshToken).where(RefreshToken.extension_session_id == browser.id)
    )


async def refresh(session, raw):
    grant = await session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == security.hash_token(raw),
            RefreshToken.audience == "ext",
        )
    )
    if grant is None or grant.extension_session_id is None:
        raise AuthError("Refresh token is unknown or revoked.")
    browser = await session.scalar(
        select(ExtensionSession)
        .where(ExtensionSession.id == grant.extension_session_id)
        .with_for_update()
    )
    if browser is None or browser.revoked_at is not None:
        raise AuthError("Browser session revoked; connect again.")
    # Lock the session before its grants so rotation and revocation serialize.
    await session.refresh(grant)
    if grant.used_at is not None:
        await revoke(session, browser)
        await session.commit()
        raise AuthError("Refresh token reused; browser session revoked.")
    if grant.expires_at <= utcnow_naive() or grant.user_id != browser.user_id:
        raise AuthError("Refresh token expired; connect again.")
    user = await session.get(User, browser.user_id)
    if user is None:
        raise AuthError("Account is gone; sign in again.")
    check_account(user, "ext")
    grant.used_at = utcnow_naive()
    browser.last_used_at = utcnow_naive()
    result = issue_pair(session, browser)
    await session.commit()
    return result


async def user_for_claims(session, claims):
    sid = claims.get("sid")
    if not isinstance(sid, str) or not sid:
        raise AuthError("Browser session missing; connect again.")
    row = (
        await session.execute(
            select(ExtensionSession, User)
            .join(User, User.id == ExtensionSession.user_id)
            .where(
                ExtensionSession.id == sid,
                ExtensionSession.user_id == claims["sub"],
                ExtensionSession.revoked_at.is_(None),
            )
        )
    ).one_or_none()
    if row is None:
        raise AuthError("Browser session revoked; connect again.")
    browser, user = row
    check_account(user, "ext")
    if (
        browser.last_used_at is None
        or browser.last_used_at < utcnow_naive() - timedelta(minutes=5)
    ):
        browser.last_used_at = utcnow_naive()
        await session.commit()
    return to_user_out(user)


async def sessions(session, user_id):
    rows = await session.scalars(
        select(ExtensionSession)
        .where(
            ExtensionSession.user_id == user_id,
            ExtensionSession.revoked_at.is_(None),
        )
        .order_by(ExtensionSession.created_at, ExtensionSession.id)
    )
    return [session_out(row) for row in rows]


async def revoke_owned(session, user_id, browser_id):
    browser = await session.scalar(
        select(ExtensionSession)
        .where(ExtensionSession.id == browser_id, ExtensionSession.user_id == user_id)
        .with_for_update()
    )
    if browser is None:
        raise NotFoundError("Browser session not found.")
    await revoke(session, browser)
    await session.commit()


async def logout(session, user_id, browser_id, raw):
    grant = await session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == security.hash_token(raw),
            RefreshToken.extension_session_id == browser_id,
            RefreshToken.user_id == user_id,
            RefreshToken.audience == "ext",
        )
    )
    if grant is None:
        raise AuthError("Refresh token does not belong to this browser session.")
    await revoke_owned(session, user_id, browser_id)
